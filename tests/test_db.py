import pytest

from sela import db
from sela.setelan import muat_setelan
from tests.conftest import ENV

TABEL = {"users", "series", "series_sources", "chapters", "chapter_sources", "archives", "reading_progress",
         "chapter_reads", "series_visits", "jobs", "activity", "kv"}


def test_migrasi_idempoten_dan_wal(tmp_path):
    conn = db.buka(tmp_path / "s.db")
    db.migrasi(conn)
    db.migrasi(conn)
    assert TABEL <= {r[0] for r in conn.execute("select name from sqlite_master where type='table'")}
    assert conn.execute("pragma journal_mode").fetchone()[0] == "wal"


def test_setelan_bawaan_dan_batas_paralel():
    s = muat_setelan(ENV)
    assert (s.chapter_paralel, s.request_per_situs, s.allowed_emails) == (3, 8, {"a@x.com", "b@x.com"})
    assert muat_setelan({**ENV, "SELA_CHAPTER_PARALEL": "9"}).chapter_paralel == 4
    with pytest.raises(ValueError):
        muat_setelan({k: v for k, v in ENV.items() if k != "SELA_ALLOWED_EMAILS"})


def test_transaksi_rollback_saat_error(conn):
    with pytest.raises(RuntimeError):
        with db.transaksi(conn):
            db.kv_set(conn, "x", "1")
            raise RuntimeError("gagal")
    assert db.kv_ambil(conn, "x") is None
    with db.transaksi(conn):
        db.kv_set(conn, "x", "2")
    assert db.kv_ambil(conn, "x") == "2"


def test_pastikan_pengguna(conn, setelan):
    db.pastikan_pengguna(conn, setelan)
    db.pastikan_pengguna(conn, setelan)
    assert dict(conn.execute("select email, peran from users").fetchall()) == {"a@x.com": "admin", "b@x.com": "pembaca"}
