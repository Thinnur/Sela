import pytest

from sela import db
from sela.progres import (KonflikRev, Posisi, ambil_posisi, batalkan_selesai, catat_kunjungan, jumlah_baru, set_latar,
                          simpan_posisi, tandai_selesai)


@pytest.fixture
def dua(conn, setelan):
    db.pastikan_pengguna(conn, setelan)
    conn.execute("insert into series(id, judul, ditambahkan_pada) values(1, 'X', 0)")
    for i in range(1, 11):
        conn.execute("insert into chapters(id, series_id, label, label_normal, kunci_urut, status, siap_pada) "
                     "values(?, 1, ?, ?, ?, 'siap', ?)", (i, f"Chapter {i}", str(i), i, 100.0 * i))
    return conn


def status_baca(conn, user, ch):
    r = conn.execute("select status from chapter_reads where user_id=? and chapter_id=?", (user, ch)).fetchone()
    return r[0] if r else None


def test_rev_dan_konflik(dua):
    assert simpan_posisi(dua, 1, 1, 3, 4, 0.5, rev_dasar=0).rev == 1
    assert simpan_posisi(dua, 1, 1, 3, 5, 0.1, rev_dasar=1).rev == 2
    with pytest.raises(KonflikRev) as e:
        simpan_posisi(dua, 1, 1, 3, 9, 0.9, rev_dasar=1)
    assert e.value.sekarang == Posisi(3, 5, 0.1, 2)


def test_progres_terpisah_per_akun(dua):
    simpan_posisi(dua, 1, 1, 3, 2, 0.4, 0)
    simpan_posisi(dua, 2, 1, 8, 7, 0.2, 0)
    assert ambil_posisi(dua, 1, 1) == Posisi(3, 2, 0.4, 1)
    assert ambil_posisi(dua, 2, 1) == Posisi(8, 7, 0.2, 1)
    assert status_baca(dua, 1, 3) == "dibaca" and status_baca(dua, 2, 3) is None


def test_posisi_tidak_sah_ditolak(dua):
    for indeks, fraksi, ch in [(-1, 0.5, 3), (0, 1.5, 3)]:
        with pytest.raises(ValueError):
            simpan_posisi(dua, 1, 1, ch, indeks, fraksi, 0)
    dua.execute("insert into series(id, judul, ditambahkan_pada) values(2, 'Y', 0)")
    with pytest.raises(ValueError):
        simpan_posisi(dua, 1, 2, 3, 0, 0.0, 0)


def test_selesai_dan_batal_tidak_ganggu_chapter_lain(dua):
    tandai_selesai(dua, 1, 2, 10.0)
    tandai_selesai(dua, 1, 3, 11.0)
    simpan_posisi(dua, 1, 1, 3, 0, 0.0, 0)
    assert status_baca(dua, 1, 3) == "selesai"
    batalkan_selesai(dua, 1, 3, 12.0)
    assert (status_baca(dua, 1, 2), status_baca(dua, 1, 3)) == ("selesai", "dibaca")


def test_jumlah_baru(dua):
    assert jumlah_baru(dua, 1, 1) == 10
    catat_kunjungan(dua, 1, 1, 750.0)
    assert jumlah_baru(dua, 1, 1) == 3
    tandai_selesai(dua, 1, 9, 800.0)
    assert jumlah_baru(dua, 1, 1) == 2 and jumlah_baru(dua, 2, 1) == 10


def test_latar(dua):
    set_latar(dua, 1, "kertas")
    assert dua.execute("select latar_reader from users where id=1").fetchone()[0] == "kertas"
    assert dua.execute("select latar_reader from users where id=2").fetchone()[0] == "gelap"
    with pytest.raises(ValueError):
        set_latar(dua, 1, "biru")
