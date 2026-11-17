import re
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from sela import db
from sela.drive import DriveLokal
from sela.web import Layanan, buat_app

BASE = "https://sela.akzara.id"


@pytest.fixture
def app(tmp_path, setelan):
    s = replace(setelan, dev_login=True)
    p = tmp_path / "h.db"
    c = db.buka(p)
    db.migrasi(c)
    db.pastikan_pengguna(c, s)
    c.execute("update users set nama='Fathin' where id=1")
    c.execute("insert into series(id, judul, jenis, sinopsis, ditambahkan_pada) values(1, 'Money Keeps Piling Up', 'manhua', 'Saldo bertambah.', 1)")
    c.execute("insert into series(id, judul, jenis, ditambahkan_pada) values(2, 'Pedang Senja', 'manhwa', 2)")
    c.execute("insert into series_sources(id, series_id, adapter, url, peran, cek_sukses_terakhir) values(1, 1, 'komiku', 'https://komiku.org/manga/m/', 'utama', 0)")
    c.execute("insert into series_sources(id, series_id, adapter, url, peran) values(2, 1, 'komikindo', 'https://komikindo.ch/komik/m/', 'cadangan')")
    c.execute("insert into series_sources(id, series_id, adapter, url, peran) values(3, 2, 'komiku', 'https://komiku.org/manga/p/', 'utama')")
    bab = [(1, "Chapter 1", "1", "siap", None), (2, "Chapter 2", "2", "siap", None), (3, "Chapter 3", "3", "siap", None),
           (4, "Chapter 3.5", "3.5", "siap", None), (5, "Chapter 4", "4", "gagal", "gambar ke-2 rusak"),
           (6, "Chapter 5", "5", "mengunduh", None)]
    for cid, label, ln, st, pesan in bab:
        c.execute("insert into chapters(id, series_id, label, label_normal, kunci_urut, status, pesan_status, siap_pada) "
                  "values(?, 1, ?, ?, ?, ?, ?, ?)", (cid, label, ln, float(ln), st, pesan, 10.0 if st == "siap" else None))
        c.execute("insert into chapter_sources values(?, 1, ?)", (cid, f"https://komiku.org/m-{ln}/"))
        if st == "siap":
            c.execute("insert into archives values(?, 'F', 1, 1000, 'm', 's', 4, '{\"gambar\": []}', 0)", (cid,))
    c.execute("insert into chapter_sources values(5, 2, 'https://komikindo.ch/m-4/')")
    c.execute("insert into chapters(id, series_id, label, label_normal, kunci_urut, status) values(7, 2, 'Chapter 1', '1', 1, 'antre')")
    c.execute("insert into reading_progress values(1, 1, 2, 1, 0.5, 1, 100)")
    c.execute("insert into chapter_reads values(1, 1, 'selesai', 50)")
    c.close()
    return buat_app(s, Layanan(lambda: db.buka(p), None, DriveLokal(tmp_path / "d"), None))


def masuk(app, uid):
    c = TestClient(app, base_url=BASE, headers={"origin": BASE}, client=("127.0.0.1", 5000))
    c.get(f"/dev/masuk/{uid}")
    return c


def html(app, url, uid=1):
    r = masuk(app, uid).get(url)
    assert r.status_code == 200, r.text
    return r.text


def test_beranda(app):
    h = html(app, "/")
    assert all(t in h for t in ["Rak bersama", "Lanjut baca", "Tambah link", "Cari di rak", "Money Keeps Piling Up"])
    assert 'href="/baca/2"' in h and "Hai, Fathin" in h


def test_beranda_tanpa_bacaan_mengajak_mulai(app):
    h = html(app, "/", uid=2)
    assert "Mulai baca" in h and 'href="/baca/1"' in h


def test_detail_dua_kolom_dan_label_asli(app):
    h = html(app, "/judul/1")
    assert "Arsip, berlaku bersama" in h and "Bacaanmu" in h and ">Chapter 3.5<" in h
    assert "Lanjut chapter 2" in h and "ekstra" in h


def test_detail_gagal_ada_coba_lagi_dan_cadangan(app):
    h = html(app, "/judul/1")
    assert "gambar ke-2 rusak" in h and 'data-url="/api/chapter/5/coba-lagi"' in h
    assert 'data-url="/api/chapter/5/ambil-cadangan"' in h and "Ambil dari KomikIndo" in h
    assert 'data-url="/api/chapter/6/ambil-cadangan"' not in h


def test_detail_status_baca_per_akun(app):
    assert "Selesai" in html(app, "/judul/1") and "Dibaca" in html(app, "/judul/1")
    h2 = html(app, "/judul/1", uid=2)
    assert "Dibaca " not in h2 and "Lanjut chapter" not in h2


def test_pita_milik_akun_aktif(app):
    assert html(app, "/").count('class="pita"') >= 1
    assert html(app, "/", uid=2).count('class="pita"') == 0


def test_rak_cari_dan_filter(app):
    h = html(app, "/rak?q=pedang")
    assert "Pedang Senja" in h and "Money Keeps" not in h
    h = html(app, "/rak?f=manhua")
    assert "Money Keeps" in h and "Pedang Senja" not in h


def test_akun_admin_saja_yang_lihat_drive(app):
    assert "Sambungkan Drive" in html(app, "/akun")
    assert "Sambungkan Drive" not in html(app, "/akun", uid=2)


def test_aktivitas(app):
    assert "Aktivitas" in html(app, "/aktivitas")


def test_judul_tidak_ada_404(app):
    assert masuk(app, 1).get("/judul/99").status_code == 404


@pytest.mark.parametrize("url", ["/", "/rak", "/judul/1", "/aktivitas", "/akun", "/masuk"])
def test_patuh_csp_tanpa_inline(app, url):
    h = html(app, url)
    assert not re.search(r"\sstyle=", h), "atribut style inline diblokir CSP"
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", h), "script inline diblokir CSP"
    assert not re.search(r"\son[a-z]+=", h), "handler inline diblokir CSP"
