import asyncio
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from sela import db
from sela.cache import CacheChapter
from sela.cbz import buat_cbz, periksa_gambar
from sela.drive import DriveLokal
from sela.web import Layanan, buat_app
from tests.gambar import jpeg_bytes, webp_bytes
from tests.test_tambah import URL_KOMIKU, pengambil_fixture

BASE = "https://sela.akzara.id"


class Lingkungan:
    def __init__(self, tmp_path, setelan):
        self.s = replace(setelan, dev_login=True)
        self.path_db = tmp_path / "api.db"
        c = db.buka(self.path_db)
        db.migrasi(c)
        db.pastikan_pengguna(c, self.s)
        c.execute("insert into series(id, judul, ditambahkan_pada) values(1, 'X', 0)")
        c.execute("insert into series_sources(id, series_id, adapter, url, peran) values(1, 1, 'komiku', 'https://komiku.org/manga/x/', 'utama')")
        for i in (1, 2):
            c.execute("insert into chapters(id, series_id, label, label_normal, kunci_urut, status) values(?, 1, ?, ?, ?, 'siap')",
                      (i, f"Chapter {i}", str(i), i))
        c.close()
        self.drive = DriveLokal(tmp_path / "drive")
        self.cache = CacheChapter(tmp_path / "cache", 10_000_000, self.drive)
        self.l = Layanan(lambda: db.buka(self.path_db), pengambil_fixture(), self.drive, self.cache)
        self.app = buat_app(self.s, self.l)

    def db(self):
        return db.buka(self.path_db)

    def client(self, uid):
        c = TestClient(self.app, base_url=BASE, headers={"origin": BASE}, client=("127.0.0.1", 5000))
        c.__enter__()
        c.get(f"/dev/masuk/{uid}")
        return c

    def arsip(self, tmp_path, chapter_id=1):
        berkas = []
        for i, data in enumerate([webp_bytes(), jpeg_bytes()]):
            p = tmp_path / f"g{chapter_id}{i}"
            p.write_bytes(data)
            berkas.append((p, periksa_gambar(data), "img.komiku.org"))
        h = buat_cbz(tmp_path / f"c{chapter_id}.cbz", berkas, {})
        b = asyncio.run(self.drive.unggah(h.path, "c.cbz", "x", {}))
        c = self.db()
        c.execute("insert into archives values(?,?,1,?,?,?,?,?,0)",
                  (chapter_id, b.id, h.ukuran, h.md5, h.sha256, h.jumlah, __import__("json").dumps(h.manifest)))
        c.close()


@pytest.fixture
def env(tmp_path, setelan):
    return Lingkungan(tmp_path, setelan)


def test_progres_abaikan_user_id_klien(env):
    putri = env.client(2)
    r = putri.post("/api/progres", json={"series_id": 1, "chapter_id": 2, "indeks": 3, "fraksi": 0.5, "rev": 0, "user_id": 1})
    assert r.status_code == 200 and r.json() == {"rev": 1}
    c = env.db()
    assert [tuple(x) for x in c.execute("select user_id from reading_progress")] == [(2,)]


def test_progres_409_kembalikan_posisi(env):
    f = env.client(1)
    badan = {"series_id": 1, "chapter_id": 2, "indeks": 3, "fraksi": 0.5, "rev": 0}
    assert f.post("/api/progres", json=badan).status_code == 200
    r = f.post("/api/progres", json=badan)
    assert r.status_code == 409 and r.json()["posisi"] == {"chapter_id": 2, "indeks": 3, "fraksi": 0.5, "rev": 1}


def test_gambar_dari_cache_header(env, tmp_path):
    env.arsip(tmp_path)
    r = env.client(1).get("/api/chapter/1/gambar/1")
    assert r.status_code == 200 and r.content == webp_bytes()
    assert r.headers["cache-control"] == "private, max-age=86400" and r.headers["content-type"] == "image/webp"
    assert env.client(1).get("/api/chapter/1/gambar/9").status_code == 404
    assert env.client(1).get("/api/chapter/2/gambar/1").status_code == 404


def test_prefetch_berikut(env, tmp_path):
    env.arsip(tmp_path, 1)
    env.arsip(tmp_path, 2)
    f = env.client(1)
    assert f.post("/api/chapter/1/prefetch-berikut").status_code == 204
    for _ in range(50):
        if (tmp_path / "cache" / "2.cbz").exists():
            break
        f.get("/masuk")
    assert (tmp_path / "cache" / "2.cbz").exists()


def test_tambah_dua_kali_satu_series(env):
    f = env.client(1)
    pv = f.post("/api/tambah/pratinjau", json={"url": URL_KOMIKU}).json()
    assert pv["judul"] == "Money Keeps Piling Up No Matter How Much I Spend" and pv["jumlah"] == 27
    assert pv["cadangan"] == {"situs": "KomikIndo", "jumlah": 26}
    a = f.post("/api/tambah", json={"url": URL_KOMIKU, "tautkan_cadangan": True}).json()["series_id"]
    b = f.post("/api/tambah", json={"url": URL_KOMIKU, "tautkan_cadangan": True}).json()["series_id"]
    assert a == b
    c = env.db()
    assert c.execute("select count(*) from series where judul like 'Money%'").fetchone()[0] == 1
    assert c.execute("select sampul from series where id=?", (a,)).fetchone()[0] == f"{a}.webp"
    assert f.post("/api/tambah/pratinjau", json={"url": URL_KOMIKU}).json() == {"series_id": a}
    assert f.get(f"/sampul/{a}").headers["cache-control"] == "private, max-age=86400"


def test_tambah_link_tidak_didukung(env):
    r = env.client(1).post("/api/tambah/pratinjau", json={"url": "https://contoh.com/komik/x"})
    assert r.status_code == 422 and "belum didukung" in r.json()["galat"]


def test_ambil_cadangan_hanya_jika_ada(env):
    f = env.client(1)
    assert f.post("/api/chapter/1/ambil-cadangan").status_code == 404
    c = env.db()
    c.execute("insert into series_sources(id, series_id, adapter, url, peran) values(2, 1, 'komikindo', 'https://komikindo.ch/komik/x/', 'cadangan')")
    c.execute("insert into chapter_sources values(1, 2, 'https://komikindo.ch/x-chapter-1/')")
    assert f.post("/api/chapter/1/ambil-cadangan").status_code == 202
    assert c.execute("select count(*) from jobs where target=1 and sumber_id=2").fetchone()[0] == 1


def test_latar_per_akun(env):
    assert env.client(1).post("/api/akun/latar", json={"latar": "kertas"}).status_code == 204
    assert env.client(1).post("/api/akun/latar", json={"latar": "biru"}).status_code == 422
    c = env.db()
    assert dict(c.execute("select id, latar_reader from users").fetchall()) == {1: "kertas", 2: "gelap"}


def test_pembaca_tidak_bisa_ganti_sumber_utama(env):
    assert env.client(2).post("/api/series/1/sumber-utama", json={"sumber_id": 1}).status_code == 403


def test_cek_manual_dan_jeda_antrean(env):
    f = env.client(1)
    assert f.post("/api/series/1/cek").json() == {"diterima": True}
    assert f.post("/api/series/1/cek").json() == {"diterima": False}
    assert f.post("/api/antrean/jeda").status_code == 204
    assert f.get("/api/aktivitas").json()["antrean_jeda"] is True
    assert f.post("/api/antrean/lanjut").status_code == 204
    assert f.get("/api/aktivitas").json()["antrean_jeda"] is False


def test_aktivitas_isi(env):
    a = env.client(2).get("/api/aktivitas").json()
    assert set(a) == {"aktivitas", "berjalan", "sumber", "drive_status", "antrean_jeda", "disk"}
    assert a["disk"]["anggaran"] == 1_500_000_000
