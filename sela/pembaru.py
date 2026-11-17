import random
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass

from sela import db
from sela.adapters import ADAPTER, adapter_untuk
from sela.fetch import PengambilAman, SumberError
from sela.ingest import _unik_per_label, buat_job_unduh, catat, pastikan_chapter
from sela.setelan import Setelan

NAMA_SITUS = {"komiku": "Komiku", "komikindo": "KomikIndo"}
MAKS_HILANG = 2


@dataclass(frozen=True)
class HasilCek:
    baru: int
    anomali: str | None


def _galat(conn: sqlite3.Connection, sumber_id: int, jenis: str, pesan: str) -> HasilCek:
    conn.execute("update series_sources set jenis_error=?, pesan_error=? where id=?", (jenis, pesan, sumber_id))
    return HasilCek(0, pesan)


async def cek_sumber(conn: sqlite3.Connection, p: PengambilAman, sumber_id: int, jam: float) -> HasilCek:
    """Bandingkan daftar chapter sumber dengan yang sudah dikenal. Tidak pernah menghapus apa pun."""
    sumber = conn.execute("select * from series_sources where id=?", (sumber_id,)).fetchone()
    conn.execute("update series_sources set cek_terakhir=? where id=?", (jam, sumber_id))
    try:
        judul = await ADAPTER[sumber["adapter"]].ambil_judul(p, sumber["url"])
    except SumberError as e:
        return _galat(conn, sumber_id, e.jenis, e.pesan)
    dikenal = {r[0] for r in conn.execute("select c.label_normal from chapter_sources cs join chapters c on c.id=cs.chapter_id "
                                         "where cs.sumber_id=?", (sumber_id,))}
    url_dikenal = {r[0] for r in conn.execute("select url from chapter_sources where sumber_id=?", (sumber_id,))}
    daftar = _unik_per_label(judul.chapters)
    hilang = dikenal - {ln for ln, _ in daftar}
    if not daftar or len(hilang) > MAKS_HILANG:
        return _galat(conn, sumber_id, "berubah", f"Daftar chapter {NAMA_SITUS[sumber['adapter']]} tidak wajar "
                                                  f"({len(daftar)} ditemukan, {len(hilang)} hilang). Data lama tetap disimpan.")
    sid, situs = sumber["series_id"], NAMA_SITUS[sumber["adapter"]]
    cadangan = sumber["peran"] == "cadangan"
    baru = 0
    with db.transaksi(conn):
        for ln, c in daftar:
            if ln in dikenal or c.url in url_dikenal:
                continue
            cid, dibuat = pastikan_chapter(conn, sid, sumber_id, ln, c, "hanya_cadangan" if cadangan else "antre")
            if dibuat:
                catat(conn, jam, "chapter_baru", f"{c.label} {'ada di' if cadangan else 'terbit di'} {situs}", sid, cid)
                baru += 1
            status = conn.execute("select status from chapters where id=?", (cid,)).fetchone()[0]
            if not cadangan and status in ("antre", "hanya_cadangan") and not conn.execute(
                    "select 1 from archives where chapter_id=?", (cid,)).fetchone():
                conn.execute("update chapters set status='antre', pesan_status=null where id=?", (cid,))
                buat_job_unduh(conn, cid, sumber_id, jam)
        conn.execute("update series_sources set cek_sukses_terakhir=?, jenis_error=null, pesan_error=null where id=?",
                     (jam, sumber_id))
    return HasilCek(baru, None)


async def detak(conn: sqlite3.Connection, p: PengambilAman, s: Setelan, jam: float,
                acak: Callable[[float, float], float] = random.uniform) -> set[str]:
    """Cek sumber utama yang jatuh tempo; kalau gagal, cek cadangannya. Mengembalikan situs yang ceknya sukses."""
    sehat = set()
    jatuh_tempo = conn.execute("select * from series_sources where peran='utama' and coalesce(cek_berikutnya, 0) <= ?",
                               (jam,)).fetchall()
    for utama in jatuh_tempo:
        diperiksa = [utama]
        hasil = await cek_sumber(conn, p, utama["id"], jam)
        if hasil.anomali is None:
            sehat.add(utama["adapter"])
        else:
            for cad in conn.execute("select * from series_sources where series_id=? and peran='cadangan'",
                                    (utama["series_id"],)).fetchall():
                diperiksa.append(cad)
                if (await cek_sumber(conn, p, cad["id"], jam)).anomali is None:
                    sehat.add(cad["adapter"])
        for sb in diperiksa:
            conn.execute("update series_sources set cek_berikutnya=? where id=?",
                         (jam + s.interval_cek + acak(-s.jitter_cek, s.jitter_cek), sb["id"]))
    return sehat


def minta_cek_manual(conn: sqlite3.Connection, series_id: int, jam: float, cooldown: int) -> bool:
    r = conn.execute("select id, cek_manual_terakhir from series_sources where series_id=? and peran='utama'",
                     (series_id,)).fetchone()
    if r is None or (r["cek_manual_terakhir"] is not None and jam - r["cek_manual_terakhir"] < cooldown):
        return False
    conn.execute("update series_sources set cek_berikutnya=?, cek_manual_terakhir=? where id=?", (jam, jam, r["id"]))
    return True


def ambil_dari_cadangan(conn: sqlite3.Connection, chapter_id: int) -> int:
    r = conn.execute("select cs.sumber_id from chapter_sources cs join series_sources ss on ss.id=cs.sumber_id "
                     "where cs.chapter_id=? and ss.peran='cadangan'", (chapter_id,)).fetchone()
    if r is None:
        raise LookupError("chapter ini tidak ada di sumber cadangan")
    with db.transaksi(conn):
        conn.execute("update jobs set status='gagal', jenis_error='dibatalkan', pesan_error='Diganti ke sumber cadangan' "
                     "where target=? and jenis='unduh_chapter' and status='antre' and sumber_id != ?", (chapter_id, r[0]))
        conn.execute("update chapters set status='antre', pesan_status=null where id=? and status != 'siap'", (chapter_id,))
        return buat_job_unduh(conn, chapter_id, r[0], time.time())


async def tautkan_cadangan(conn: sqlite3.Connection, p: PengambilAman, series_id: int, url: str, jam: float) -> int:
    a = adapter_untuk(url)
    url = a.normalisasi(url)
    utama = conn.execute("select adapter from series_sources where series_id=? and peran='utama'", (series_id,)).fetchone()
    if utama is None or utama["adapter"] == a.nama:
        raise ValueError("cadangan harus dari situs yang berbeda dengan sumber utama")
    if conn.execute("select 1 from series_sources where series_id=? and peran='cadangan'", (series_id,)).fetchone():
        raise ValueError("judul ini sudah punya cadangan")
    if conn.execute("select 1 from series_sources where url=?", (url,)).fetchone():
        raise ValueError("link ini sudah dipakai judul lain")
    sumber_id = conn.execute("insert into series_sources(series_id, adapter, url, peran, cek_berikutnya) "
                             "values(?,?,?,'cadangan',?)", (series_id, a.nama, url, jam)).lastrowid
    hasil = await cek_sumber(conn, p, sumber_id, jam)
    if hasil.anomali:
        raise SumberError("berubah", hasil.anomali)
    return sumber_id


def ganti_sumber_utama(conn: sqlite3.Connection, series_id: int, sumber_id: int) -> None:
    with db.transaksi(conn):
        lama = conn.execute("select id from series_sources where series_id=? and peran='utama'", (series_id,)).fetchone()[0]
        if lama == sumber_id:
            return
        if not conn.execute("select 1 from series_sources where id=? and series_id=?", (sumber_id, series_id)).fetchone():
            raise LookupError("sumber tidak ditemukan untuk judul ini")
        conn.execute("update series_sources set peran='cadangan' where id=?", (lama,))
        conn.execute("update series_sources set peran='utama' where id=?", (sumber_id,))
        conn.execute("update jobs set status='gagal', jenis_error='dibatalkan', pesan_error='Sumber utama diganti' "
                     "where sumber_id=? and jenis='unduh_chapter' and status='antre'", (lama,))
        menunggu = conn.execute(
            "select c.id from chapters c join chapter_sources cs on cs.chapter_id=c.id and cs.sumber_id=? "
            "where c.series_id=? and c.status != 'siap' and not exists(select 1 from archives a where a.chapter_id=c.id) "
            "and not exists(select 1 from jobs j where j.target=c.id and j.status='berjalan')",
            (sumber_id, series_id)).fetchall()
        jam = time.time()
        for r in menunggu:
            conn.execute("update chapters set status='antre', pesan_status=null where id=?", (r[0],))
            buat_job_unduh(conn, r[0], sumber_id, jam)
