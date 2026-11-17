from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from sela import db
from sela.auth import izinkan_login
from sela.web import CSP, Layanan, buat_app

BASE = "https://sela.akzara.id"


@pytest.fixture
def path_db(tmp_path, setelan):
    p = tmp_path / "a.db"
    c = db.buka(p)
    db.migrasi(c)
    db.pastikan_pengguna(c, setelan)
    c.close()
    return p


def app_uji(setelan, path_db, **ubah):
    s = replace(setelan, **ubah)
    return buat_app(s, Layanan(lambda: db.buka(path_db), None, None, None))


@pytest.fixture
def client(setelan, path_db):
    return TestClient(app_uji(setelan, path_db), base_url=BASE, headers={"origin": BASE})


@pytest.fixture
def client_masuk(setelan, path_db):
    c = TestClient(app_uji(setelan, path_db, dev_login=True), base_url=BASE, headers={"origin": BASE}, client=("127.0.0.1", 5000))
    assert c.get("/dev/masuk/1", follow_redirects=False).status_code == 303
    return c


def test_login_pertama_ikat_sub_lalu_cocok_lewat_sub(conn, setelan):
    db.pastikan_pengguna(conn, setelan)
    assert izinkan_login(conn, setelan, {"sub": "S1", "email": "a@x.com", "email_verified": True, "name": "Fathin"}) == 1
    assert izinkan_login(conn, setelan, {"sub": "S1", "email": "baru@x.com", "email_verified": True}) == 1
    assert conn.execute("select google_sub, nama from users where id=1").fetchone()[:] == ("S1", "Fathin")


@pytest.mark.parametrize("info", [
    {"sub": "S9", "email": "c@x.com", "email_verified": True},
    {"sub": "S2", "email": "b@x.com", "email_verified": False},
    {"sub": "LAIN", "email": "a@x.com", "email_verified": True},
])
def test_login_ditolak(conn, setelan, info):
    db.pastikan_pengguna(conn, setelan)
    izinkan_login(conn, setelan, {"sub": "S1", "email": "a@x.com", "email_verified": True})
    assert izinkan_login(conn, setelan, info) is None


def test_rute_html_redirect_api_401(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/masuk"
    for u in ["/api/chapter/1/gambar/1", "/sampul/1", "/api/aktivitas"]:
        r = client.get(u)
        assert r.status_code == 401 and r.json() == {"galat": "sesi_habis"}


def test_halaman_masuk_publik(client):
    r = client.get("/masuk")
    assert r.status_code == 200 and "Masuk dengan Google" in r.text


@pytest.mark.parametrize("url,judul", [("/privasi", "Kebijakan privasi"), ("/ketentuan", "Ketentuan penggunaan")])
def test_privasi_dan_ketentuan_publik(client, url, judul):
    r = client.get(url, follow_redirects=False)
    assert r.status_code == 200 and judul in r.text and "drive.file" in client.get("/privasi").text
    assert 'href="/privasi"' in client.get("/masuk").text and 'href="/ketentuan"' in client.get("/masuk").text


def test_post_origin_asing_403(client_masuk):
    assert client_masuk.post("/api/progres", headers={"origin": "https://evil.x"}).status_code == 403
    assert client_masuk.post("/api/progres", headers={"origin": ""}).status_code == 403


def test_header_keamanan(client):
    r = client.get("/masuk")
    assert r.headers["content-security-policy"] == CSP
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["referrer-policy"] == "same-origin"


def test_dev_login_mati_bawaan(client):
    assert client.get("/dev/masuk/1").status_code == 404


def test_dev_login_hanya_loopback(setelan, path_db):
    c = TestClient(app_uji(setelan, path_db, dev_login=True), base_url=BASE, client=("203.0.113.5", 5000))
    assert c.get("/dev/masuk/1").status_code == 404


def test_masuk_lalu_keluar(client_masuk):
    assert client_masuk.get("/", follow_redirects=False).status_code == 200
    assert client_masuk.post("/keluar", follow_redirects=False).status_code == 303
    assert client_masuk.get("/", follow_redirects=False).status_code == 303


def test_email_dihapus_dari_allowlist_mencabut_akses(setelan, path_db):
    c = db.buka(path_db)
    assert izinkan_login(c, setelan, {"sub": "S2", "email": "b@x.com", "email_verified": True}) == 2
    tanpa_b = replace(setelan, allowed_emails=frozenset({"a@x.com"}))
    assert izinkan_login(c, tanpa_b, {"sub": "S2", "email": "b@x.com", "email_verified": True}) is None
    c.close()
    k = TestClient(app_uji(tanpa_b, path_db, dev_login=True), base_url=BASE, client=("127.0.0.1", 1))
    k.get("/dev/masuk/2")
    assert k.get("/", follow_redirects=False).status_code == 303
    assert k.get("/api/aktivitas").status_code == 401
