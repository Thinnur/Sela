import sqlite3
from contextlib import contextmanager
from pathlib import Path

from sela.setelan import Setelan

SKEMA = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, google_sub TEXT UNIQUE, email TEXT UNIQUE NOT NULL,
  nama TEXT NOT NULL DEFAULT '', peran TEXT NOT NULL CHECK(peran IN ('admin','pembaca')),
  latar_reader TEXT NOT NULL DEFAULT 'gelap' CHECK(latar_reader IN ('gelap','kertas')));
CREATE TABLE IF NOT EXISTS series(id INTEGER PRIMARY KEY, judul TEXT NOT NULL, alias TEXT NOT NULL DEFAULT '[]',
  sinopsis TEXT NOT NULL DEFAULT '', sampul TEXT, jenis TEXT, ditambahkan_oleh INTEGER REFERENCES users(id),
  ditambahkan_pada REAL NOT NULL);
CREATE TABLE IF NOT EXISTS series_sources(id INTEGER PRIMARY KEY, series_id INTEGER NOT NULL REFERENCES series(id),
  adapter TEXT NOT NULL, url TEXT NOT NULL UNIQUE, peran TEXT NOT NULL CHECK(peran IN ('utama','cadangan')),
  cek_terakhir REAL, cek_sukses_terakhir REAL, jenis_error TEXT, pesan_error TEXT, cek_berikutnya REAL,
  cek_manual_terakhir REAL);
CREATE TABLE IF NOT EXISTS chapters(id INTEGER PRIMARY KEY, series_id INTEGER NOT NULL REFERENCES series(id),
  label TEXT NOT NULL, label_normal TEXT NOT NULL, kunci_urut REAL NOT NULL, terbit TEXT,
  status TEXT NOT NULL DEFAULT 'antre' CHECK(status IN ('antre','mengunduh','mengunggah','memverifikasi','siap',
    'menunggu_ulang','gagal','menunggu_ruang','hanya_cadangan')),
  pesan_status TEXT, siap_pada REAL, UNIQUE(series_id, label_normal));
CREATE TABLE IF NOT EXISTS chapter_sources(chapter_id INTEGER NOT NULL REFERENCES chapters(id),
  sumber_id INTEGER NOT NULL REFERENCES series_sources(id), url TEXT NOT NULL,
  PRIMARY KEY(chapter_id, sumber_id), UNIQUE(sumber_id, url));
CREATE TABLE IF NOT EXISTS archives(chapter_id INTEGER PRIMARY KEY REFERENCES chapters(id), drive_file_id TEXT NOT NULL,
  sumber_id INTEGER NOT NULL REFERENCES series_sources(id), ukuran INTEGER NOT NULL, md5 TEXT NOT NULL,
  sha256 TEXT NOT NULL, jumlah_gambar INTEGER NOT NULL, manifest TEXT NOT NULL, diverifikasi_pada REAL NOT NULL);
CREATE TABLE IF NOT EXISTS reading_progress(user_id INTEGER NOT NULL REFERENCES users(id),
  series_id INTEGER NOT NULL REFERENCES series(id), chapter_id INTEGER NOT NULL REFERENCES chapters(id),
  indeks INTEGER NOT NULL, fraksi REAL NOT NULL, rev INTEGER NOT NULL, diperbarui REAL NOT NULL,
  PRIMARY KEY(user_id, series_id));
CREATE TABLE IF NOT EXISTS chapter_reads(user_id INTEGER NOT NULL REFERENCES users(id),
  chapter_id INTEGER NOT NULL REFERENCES chapters(id), status TEXT NOT NULL CHECK(status IN ('dibaca','selesai')),
  diperbarui REAL NOT NULL, PRIMARY KEY(user_id, chapter_id));
CREATE TABLE IF NOT EXISTS series_visits(user_id INTEGER NOT NULL, series_id INTEGER NOT NULL, terakhir REAL NOT NULL,
  PRIMARY KEY(user_id, series_id));
CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY,
  jenis TEXT NOT NULL CHECK(jenis IN ('unduh_chapter','cek_update','backup_db')), target INTEGER, sumber_id INTEGER,
  status TEXT NOT NULL DEFAULT 'antre' CHECK(status IN ('antre','berjalan','selesai','gagal')),
  percobaan INTEGER NOT NULL DEFAULT 0, jalan_setelah REAL NOT NULL DEFAULT 0, kunci_idem TEXT UNIQUE,
  checkpoint TEXT NOT NULL DEFAULT '{}', jenis_error TEXT, pesan_error TEXT, dibuat REAL NOT NULL, diperbarui REAL NOT NULL);
CREATE TABLE IF NOT EXISTS activity(id INTEGER PRIMARY KEY, pada REAL NOT NULL, jenis TEXT NOT NULL, series_id INTEGER,
  chapter_id INTEGER, user_id INTEGER, teks TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS kv(kunci TEXT PRIMARY KEY, nilai TEXT NOT NULL);
"""


def buka(path: Path) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False, timeout=5, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma journal_mode=wal")
    conn.execute("pragma foreign_keys=on")
    conn.execute("pragma busy_timeout=5000")
    return conn


@contextmanager
def transaksi(conn: sqlite3.Connection):
    conn.execute("begin immediate")
    try:
        yield conn
    except BaseException:
        conn.execute("rollback")
        raise
    conn.execute("commit")


def migrasi(conn: sqlite3.Connection) -> None:
    conn.executescript(SKEMA)
    conn.execute("pragma user_version=1")


def pastikan_pengguna(conn: sqlite3.Connection, s: Setelan) -> None:
    for email in sorted(s.allowed_emails):
        peran = "admin" if email == s.admin_email else "pembaca"
        conn.execute("insert into users(email, peran) values(?, ?) on conflict(email) do update set peran=excluded.peran",
                     (email, peran))


def kv_ambil(conn: sqlite3.Connection, kunci: str) -> str | None:
    r = conn.execute("select nilai from kv where kunci=?", (kunci,)).fetchone()
    return r[0] if r else None


def kv_set(conn: sqlite3.Connection, kunci: str, nilai: str | None) -> None:
    if nilai is None:
        conn.execute("delete from kv where kunci=?", (kunci,))
    else:
        conn.execute("insert into kv values(?, ?) on conflict(kunci) do update set nilai=excluded.nilai", (kunci, nilai))
