import json
import re
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from sela import db
from sela.web import Layanan, buat_app

BASE = "https://sela.akzara.id"
LABEL = [str(i) for i in range(1, 11)] + ["10.5"] + [str(i) for i in range(11, 28)]
MANIFEST = json.dumps({"gambar": [{"n": 1, "lebar": 720, "tinggi": 1100}, {"n": 2, "lebar": 720, "tinggi": 2400}]})


@pytest.fixture
def app(tmp_path, setelan):
    s = replace(setelan, dev_login=True)
    p = tmp_path / "b.db"
    c = db.buka(p)
    db.migrasi(c)
    db.pastikan_pengguna(c, s)
    c.execute("insert into series(id, judul, ditambahkan_pada) values(1, 'Money Keeps Piling Up', 0)")
    c.execute("insert into series_sources(id, series_id, adapter, url, peran) values(1, 1, 'komiku', 'https://komiku.org/manga/m/', 'utama')")
    for i, ln in enumerate(LABEL, 1):
        status = "mengunduh" if ln == "13" else "siap"
        c.execute("insert into chapters(id, series_id, label, label_normal, kunci_urut, status) values(?, 1, ?, ?, ?, ?)",
                  (i, f"Chapter {ln}", ln, float(ln), status))
        if status == "siap":
            c.execute("insert into archives values(?, 'F', 1, 1, 'm', 's', 2, ?, 0)", (i, MANIFEST))
    c.execute("insert into chapter_reads values(1, 11, 'selesai', 0), (1, 12, 'selesai', 0)")
    c.close()
    return buat_app(s, Layanan(lambda: db.buka(p), None, None, None))


def masuk(app, uid=1):
    c = TestClient(app, base_url=BASE, headers={"origin": BASE}, client=("127.0.0.1", 5000))
    c.get(f"/dev/masuk/{uid}")
    return c


def id_label(ln):
    return LABEL.index(ln) + 1


def test_img_punya_dimensi(app):
    h = masuk(app).get(f"/baca/{id_label('12')}").text
    imgs = re.findall(r"<img [^>]*>", h.split('class="strip"')[1].split("</div>")[0])
    assert len(imgs) == 2
    assert all('width="720"' in i and 'loading="lazy"' in i and 'decoding="async"' in i for i in imgs)
    assert 'height="2400"' in imgs[1] and f'src="/api/chapter/{id_label("12")}/gambar/2"' in imgs[1]


def test_petak_akhir_chapter(app):
    h = masuk(app).get(f"/baca/{id_label('12')}").text
    assert re.findall(r'class="petak[^"]*"[^>]*>\s*<span class="fd">([^<]+)</span>', h) == ["10.5", "11", "13", "14", "15"]
    assert 'class="petak petak-belum-siap"' in h and h.count("petak-selesai") == 2


def test_berikutnya_belum_siap_tampilkan_status(app):
    h = masuk(app).get(f"/baca/{id_label('12')}").text
    assert "Lanjut chapter 13" not in h and "Mengunduh" in h


def test_berikutnya_siap_ada_tombol(app):
    h = masuk(app).get(f"/baca/{id_label('11')}").text
    assert "Lanjut chapter 12" in h and f'href="/baca/{id_label("12")}"' in h


def test_latar_dari_akun(app):
    c = masuk(app, 2)
    assert 'class="reader latar-gelap"' in c.get("/baca/1").text
    c.post("/api/akun/latar", json={"latar": "kertas"})
    assert 'class="reader latar-kertas"' in c.get("/baca/1").text
    assert 'class="reader latar-gelap"' in masuk(app, 1).get("/baca/1").text


def test_posisi_tersimpan_dipasang(app):
    c = masuk(app)
    c.post("/api/progres", json={"series_id": 1, "chapter_id": 5, "indeks": 1, "fraksi": 0.25, "rev": 0})
    h = c.get("/baca/5").text
    assert 'data-indeks="1"' in h and 'data-fraksi="0.25"' in h and 'data-rev="1"' in h
    h = c.get("/baca/6").text
    assert 'data-indeks=""' in h and 'data-rev="1"' in h


def test_chapter_belum_siap(app):
    r = masuk(app).get(f"/baca/{id_label('13')}")
    assert r.status_code == 200 and "belum siap" in r.text and "<img" not in r.text


def test_chapter_tidak_ada(app):
    assert masuk(app).get("/baca/999").status_code == 404


def test_reader_patuh_csp(app):
    h = masuk(app).get("/baca/1").text
    assert not re.search(r"\sstyle=", h) and not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", h)
