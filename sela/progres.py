import sqlite3
import time
from dataclasses import dataclass

from sela import db

LATAR = ("gelap", "kertas")


@dataclass(frozen=True)
class Posisi:
    chapter_id: int
    indeks: int
    fraksi: float
    rev: int


class KonflikRev(Exception):
    def __init__(self, sekarang: Posisi):
        super().__init__("posisi sudah diperbarui dari perangkat lain")
        self.sekarang = sekarang


def ambil_posisi(conn: sqlite3.Connection, user_id: int, series_id: int) -> Posisi | None:
    r = conn.execute("select chapter_id, indeks, fraksi, rev from reading_progress where user_id=? and series_id=?",
                     (user_id, series_id)).fetchone()
    return Posisi(*r) if r else None


def simpan_posisi(conn: sqlite3.Connection, user_id: int, series_id: int, chapter_id: int, indeks: int, fraksi: float,
                  rev_dasar: int) -> Posisi:
    if indeks < 0 or not 0.0 <= fraksi <= 1.0:
        raise ValueError("posisi tidak sah")
    with db.transaksi(conn):
        if not conn.execute("select 1 from chapters where id=? and series_id=?", (chapter_id, series_id)).fetchone():
            raise ValueError("chapter bukan milik judul ini")
        sekarang = ambil_posisi(conn, user_id, series_id)
        if (sekarang.rev if sekarang else 0) != rev_dasar:
            raise KonflikRev(sekarang)
        baru = Posisi(chapter_id, indeks, fraksi, rev_dasar + 1)
        conn.execute("insert into reading_progress values(?,?,?,?,?,?,?) on conflict(user_id, series_id) do update set "
                     "chapter_id=excluded.chapter_id, indeks=excluded.indeks, fraksi=excluded.fraksi, rev=excluded.rev, "
                     "diperbarui=excluded.diperbarui",
                     (user_id, series_id, chapter_id, indeks, fraksi, baru.rev, time.time()))
        conn.execute("insert or ignore into chapter_reads values(?, ?, 'dibaca', ?)", (user_id, chapter_id, time.time()))
    return baru


def _set_baca(conn: sqlite3.Connection, user_id: int, chapter_id: int, status: str, jam: float) -> None:
    conn.execute("insert into chapter_reads values(?,?,?,?) on conflict(user_id, chapter_id) do update set "
                 "status=excluded.status, diperbarui=excluded.diperbarui", (user_id, chapter_id, status, jam))


def tandai_selesai(conn: sqlite3.Connection, user_id: int, chapter_id: int, jam: float) -> None:
    _set_baca(conn, user_id, chapter_id, "selesai", jam)


def batalkan_selesai(conn: sqlite3.Connection, user_id: int, chapter_id: int, jam: float) -> None:
    _set_baca(conn, user_id, chapter_id, "dibaca", jam)


def jumlah_baru(conn: sqlite3.Connection, user_id: int, series_id: int) -> int:
    return conn.execute(
        "select count(*) from chapters c where c.series_id=? and c.status='siap' "
        "and c.siap_pada > coalesce((select terakhir from series_visits where user_id=? and series_id=?), 0) "
        "and not exists(select 1 from chapter_reads r where r.user_id=? and r.chapter_id=c.id)",
        (series_id, user_id, series_id, user_id)).fetchone()[0]


def catat_kunjungan(conn: sqlite3.Connection, user_id: int, series_id: int, jam: float) -> None:
    conn.execute("insert into series_visits values(?,?,?) on conflict(user_id, series_id) do update set terakhir=excluded.terakhir",
                 (user_id, series_id, jam))


def set_latar(conn: sqlite3.Connection, user_id: int, latar: str) -> None:
    if latar not in LATAR:
        raise ValueError("latar harus gelap atau kertas")
    conn.execute("update users set latar_reader=? where id=?", (latar, user_id))
