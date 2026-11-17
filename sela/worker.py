import asyncio
import errno
import logging
import os
import shutil
import sqlite3
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from sela import db
from sela.cbz import GambarRusak
from sela.drive import Drive, DriveError
from sela.fetch import PengambilAman, SumberError
from sela.ingest import proses_chapter
from sela.setelan import Setelan

JADWAL_ULANG = (60, 300, 1800, 7200)
MAKS_PERCOBAAN = 5
CADANGAN_JOB = 40_000_000  # perkiraan ruang satu chapter yang sedang diproses (gambar + CBZ)
log = logging.getLogger("sela.worker")


def ukuran_dir(path: Path) -> int:
    total = 0
    for akar, _, berkas in os.walk(path):
        for b in berkas:
            try:
                total += os.path.getsize(os.path.join(akar, b))
            except OSError:
                pass
    return total


def coba_lagi_sumber(conn: sqlite3.Connection, sumber_id: int) -> None:
    with db.transaksi(conn):
        conn.execute("update series_sources set jenis_error=null, pesan_error=null where id=?", (sumber_id,))
        conn.execute("update chapters set status='antre', pesan_status=null where id in "
                     "(select target from jobs where sumber_id=? and jenis='unduh_chapter' and status='gagal')", (sumber_id,))
        conn.execute("update jobs set status='antre', percobaan=0, jalan_setelah=0, jenis_error=null, pesan_error=null "
                     "where sumber_id=? and jenis='unduh_chapter' and status='gagal'", (sumber_id,))


def coba_lagi_chapter(conn: sqlite3.Connection, chapter_id: int) -> None:
    with db.transaksi(conn):
        conn.execute("update jobs set status='antre', percobaan=0, jalan_setelah=0, jenis_error=null, pesan_error=null "
                     "where target=? and jenis='unduh_chapter' and status='gagal'", (chapter_id,))
        conn.execute("update chapters set status='antre', pesan_status=null where id=? and status in ('gagal','menunggu_ulang')",
                     (chapter_id,))


class Worker:
    def __init__(self, s: Setelan, buka_db: Callable[[], sqlite3.Connection], p: PengambilAman | None, drive: Drive | None,
                 proses=proses_chapter, jam: Callable[[], float] = time.time, sisa_disk: Callable[[], int] | None = None,
                 detak: Callable[[], Awaitable[set[str]]] | None = None):
        self.s = s
        self.buka_db = buka_db
        self.p = p
        self.drive = drive
        self.proses = proses
        self.jam = jam
        self.sisa_disk = sisa_disk or (lambda: shutil.disk_usage(s.root).free)
        self.detak = detak
        self.berjalan: dict[int, tuple[asyncio.Task, str]] = {}
        self.turun: set[str] = set()

    def turunkan_situs(self, situs: str) -> None:
        self.turun.add(situs)

    def normalkan_situs(self, situs: str) -> None:
        self.turun.discard(situs)

    def pulihkan(self) -> None:
        conn = self.buka_db()
        try:
            with db.transaksi(conn):
                conn.execute("update jobs set status='antre' where status='berjalan'")
                conn.execute("update chapters set status='antre' where status in ('mengunduh','mengunggah','memverifikasi')")
        finally:
            conn.close()

    def _cukup_ruang(self) -> bool:
        terpakai = ukuran_dir(self.s.dir_tmp) + ukuran_dir(self.s.dir_cache)
        return terpakai + CADANGAN_JOB <= self.s.anggaran_disk and self.sisa_disk() >= self.s.sisa_disk_min

    async def satu_putaran(self) -> int:
        conn = self.buka_db()
        try:
            if db.kv_ambil(conn, "antrean_jeda") == "1" or db.kv_ambil(conn, "drive_status") == "perlu_sambung":
                return 0
            slot = self.s.chapter_paralel - len(self.berjalan)
            if slot <= 0:
                return 0
            kandidat = conn.execute(
                "select j.id, j.target, ss.adapter from jobs j join series_sources ss on ss.id=j.sumber_id "
                "where j.jenis='unduh_chapter' and j.status='antre' and j.jalan_setelah <= ? "
                "and coalesce(ss.jenis_error, '') != 'ditolak' order by j.jalan_setelah, j.id", (self.jam(),)).fetchall()
            mulai = 0
            for job in kandidat:
                if mulai >= slot:
                    break
                situs = job["adapter"]
                if situs in self.turun and any(st == situs for _, st in self.berjalan.values()):
                    continue
                if not self._cukup_ruang():
                    conn.execute("update chapters set status='menunggu_ruang', pesan_status='Menunggu ruang disk VPS' "
                                 "where id=? and status in ('antre','menunggu_ulang')", (job["target"],))
                    break
                if conn.execute("update jobs set status='berjalan', diperbarui=? where id=? and status='antre'",
                                (self.jam(), job["id"])).rowcount != 1:
                    continue
                tugas = asyncio.create_task(self._jalankan(job["id"], situs))
                self.berjalan[job["id"]] = (tugas, situs)
                mulai += 1
            return mulai
        finally:
            conn.close()

    async def _jalankan(self, job_id: int, situs: str) -> None:
        try:
            await self.proses(self.buka_db, self.p, self.drive, self.s, job_id)
        except Exception as e:  # semua kegagalan diarahkan ke status job, worker tidak boleh mati
            self.tangani_gagal(job_id, situs, e)
        finally:
            self.berjalan.pop(job_id, None)

    def tangani_gagal(self, job_id: int, situs: str, err: Exception) -> None:
        conn = self.buka_db()
        try:
            self._tangani(conn, job_id, situs, err)
        finally:
            conn.close()

    def _tangani(self, conn: sqlite3.Connection, job_id: int, situs: str, err: Exception) -> None:
        now = self.jam()
        job = conn.execute("select * from jobs where id=?", (job_id,)).fetchone()
        cid = job["target"]

        def kembali_antre(status_ch: str, pesan: str, setelah: float = 0) -> None:
            conn.execute("update jobs set status='antre', jalan_setelah=?, diperbarui=? where id=?", (setelah, now, job_id))
            conn.execute("update chapters set status=?, pesan_status=? where id=?", (status_ch, pesan, cid))

        def gagal(pesan: str, jenis: str) -> None:
            conn.execute("update jobs set status='gagal', jenis_error=?, pesan_error=?, diperbarui=? where id=?",
                         (jenis, pesan, now, job_id))
            conn.execute("update chapters set status='gagal', pesan_status=? where id=?", (pesan, cid))

        if isinstance(err, DriveError) and err.jenis == "auth":
            db.kv_set(conn, "drive_status", "perlu_sambung")
            kembali_antre("menunggu_ulang", "Drive perlu disambungkan ulang")
            return
        if isinstance(err, OSError) and err.errno == errno.ENOSPC:
            shutil.rmtree(self.s.dir_tmp / str(job_id), ignore_errors=True)
            kembali_antre("menunggu_ruang", "Menunggu ruang disk VPS")
            return
        if isinstance(err, SumberError) and err.jenis == "ditolak":
            conn.execute("update series_sources set jenis_error='ditolak', pesan_error=? where id=?", (err.pesan, job["sumber_id"]))
            gagal(f"Sumber menolak akses: {err.pesan}", "ditolak")
            return
        if isinstance(err, SumberError) and err.jenis in ("tidak_ada", "berubah", "tidak_didukung"):
            gagal(err.pesan, err.jenis)
            return

        percobaan = job["percobaan"] + 1
        pesan = err.pesan if isinstance(err, (SumberError, DriveError)) else str(err) or type(err).__name__
        jenis = err.jenis if isinstance(err, (SumberError, DriveError)) else "sementara"
        if not isinstance(err, (SumberError, DriveError, GambarRusak)):
            log.exception("job %s gagal tak terduga", job_id, exc_info=err)
        conn.execute("update jobs set percobaan=?, jenis_error=?, pesan_error=? where id=?", (percobaan, jenis, pesan, job_id))
        if percobaan >= MAKS_PERCOBAAN:
            gagal(pesan, jenis)
            return
        jeda = JADWAL_ULANG[min(percobaan, len(JADWAL_ULANG)) - 1]
        if isinstance(err, SumberError) and err.jenis == "dibatasi":
            self.turunkan_situs(situs)
            jeda = max(jeda, err.retry_after or 0)
        kembali_antre("menunggu_ulang", f"{pesan}. Dicoba lagi otomatis.", now + jeda)

    async def jalan(self) -> None:
        detak_terakhir = 0.0
        while True:
            try:
                await self.satu_putaran()
                if self.detak and time.monotonic() - detak_terakhir >= 60:
                    detak_terakhir = time.monotonic()
                    for situs in await self.detak():
                        self.normalkan_situs(situs)
            except Exception:  # putaran gagal tidak boleh menghentikan worker
                log.exception("putaran worker gagal")
            await asyncio.sleep(2)
