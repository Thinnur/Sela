import asyncio
import logging
import os
import time
from collections.abc import Callable
from pathlib import Path

from sela.drive import Drive

log = logging.getLogger("sela.cache")


class CachePenuh(Exception):
    pass


class CacheChapter:
    def __init__(self, dir: Path, maks_byte: int, drive: Drive, jam: Callable[[], float] = time.time,
                 lindung_detik: int = 1800):
        self.dir = Path(dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.maks_byte = maks_byte
        self.drive = drive
        self.jam = jam
        self.lindung_detik = lindung_detik
        self._kunci: dict[int, asyncio.Lock] = {}
        self._latar: set[asyncio.Task] = set()

    def _berkas(self, chapter_id: int) -> Path:
        return self.dir / f"{chapter_id}.cbz"

    def _sentuh(self, p: Path) -> None:
        t = self.jam()
        os.utime(p, (t, t))

    def ukuran(self) -> int:
        return sum(p.stat().st_size for p in self.dir.glob("*.cbz"))

    def _beri_ruang(self, tambahan: int) -> None:
        sekarang = self.jam()
        berkas = sorted(self.dir.glob("*.cbz"), key=lambda p: p.stat().st_mtime)
        total = sum(p.stat().st_size for p in berkas) + tambahan
        for p in berkas:
            if total <= self.maks_byte:
                return
            st = p.stat()
            if sekarang - st.st_mtime < self.lindung_detik:
                continue  # chapter yang sedang dibaca tidak boleh dibuang
            p.unlink(missing_ok=True)
            total -= st.st_size
        if total > self.maks_byte:
            raise CachePenuh("cache baca penuh oleh chapter yang sedang dibaca")

    async def path(self, chapter_id: int, file_id: str) -> Path:
        p = self._berkas(chapter_id)
        if p.exists():
            self._sentuh(p)
            return p
        async with self._kunci.setdefault(chapter_id, asyncio.Lock()):
            if p.exists():
                self._sentuh(p)
                return p
            part = p.with_suffix(".part")
            try:
                await self.drive.unduh(file_id, part)
                self._beri_ruang(part.stat().st_size)
            except BaseException:
                part.unlink(missing_ok=True)
                raise
            part.rename(p)
            self._sentuh(p)
            return p

    def prefetch(self, chapter_id: int, file_id: str) -> None:
        async def diam():
            try:
                await self.path(chapter_id, file_id)
            except Exception:  # prefetch hanya mempercepat; kegagalan tidak boleh mengganggu pembaca
                log.debug("prefetch chapter %s gagal", chapter_id, exc_info=True)

        t = asyncio.create_task(diam())
        self._latar.add(t)
        t.add_done_callback(self._latar.discard)
