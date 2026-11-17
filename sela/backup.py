import asyncio
import logging
import sqlite3
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from sela.drive import Drive

WIB = 7 * 3600  # Asia/Jakarta tanpa DST
SIMPAN = 14
log = logging.getLogger("sela.backup")


def detik_menuju(jam_target: int, sekarang: float) -> float:
    """Detik dari sekarang sampai pukul jam_target:00 WIB berikutnya."""
    lokal = (sekarang + WIB) % 86400
    sisa = jam_target * 3600 - lokal
    return sisa if sisa > 0 else sisa + 86400


async def backup_db(path_db: Path, drive: Drive, dir_tmp: Path, jam: float) -> None:
    """Salin SQLite secara konsisten, unggah ke Sela/_db, sisakan 14 salinan terbaru."""
    dir_tmp.mkdir(parents=True, exist_ok=True)
    nama = time.strftime("sela-%Y%m%d-%H%M.db", time.gmtime(jam + WIB))
    tujuan = dir_tmp / nama
    try:
        sumber, salin = sqlite3.connect(path_db), sqlite3.connect(tujuan)
        try:
            sumber.backup(salin)
        finally:
            sumber.close()
            salin.close()
        akar = await drive.pastikan_folder("Sela", None)
        folder = await drive.pastikan_folder("_db", akar)
        await drive.unggah(tujuan, nama, folder, {"sela_backup": "1"})
    finally:
        tujuan.unlink(missing_ok=True)
    semua = sorted(await drive.cari({"sela_backup": "1"}), key=lambda b: b.nama, reverse=True)
    for lama in semua[SIMPAN:]:
        await drive.hapus(lama.id)  # hanya backup DB milik Sela sendiri yang pernah dihapus


async def jadwal_harian(tugas: Callable[[], Awaitable[None]], jam_target: int = 3) -> None:
    while True:
        await asyncio.sleep(detik_menuju(jam_target, time.time()))
        try:
            await tugas()
        except Exception:  # backup gagal dicoba lagi besok; jangan matikan proses
            log.exception("backup DB harian gagal")
