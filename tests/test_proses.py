import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import pytest

from sela import db, ingest
from sela.cbz import GambarRusak
from sela.drive import DriveError, DriveLokal
from sela.fetch import PengambilAman
from tests.gambar import jpeg_bytes, png_bytes, webp_bytes

URL_CH = "https://komiku.org/x-chapter-1/"
HTML = '<div id="Baca_Komik">' + "".join(f'<img data-src="https://img.komiku.org/{i}.jpg">' for i in range(3)) + "</div>"


@dataclass
class Env:
    path_db: Path
    s: object
    drive: DriveLokal
    gambar: list = field(default_factory=lambda: [webp_bytes(), jpeg_bytes(), png_bytes()])
    conn: object = None
    p: object = None

    def args(self, job_id):
        return (lambda: db.buka(self.path_db), self.p, self.drive, self.s, job_id)


@pytest.fixture
def env(tmp_path, setelan):
    e = Env(tmp_path / "s.db", setelan, DriveLokal(tmp_path / "drive"))
    e.conn = db.buka(e.path_db)
    db.migrasi(e.conn)
    db.pastikan_pengguna(e.conn, setelan)

    def handler(request):
        if str(request.url) == URL_CH:
            return httpx.Response(200, text=HTML)
        return httpx.Response(200, content=e.gambar[int(request.url.path.strip("/").split(".")[0])])

    e.p = PengambilAman(httpx.AsyncClient(transport=httpx.MockTransport(handler)), resolver=lambda h: ["93.184.216.34"])
    c = e.conn
    c.execute("insert into series(id, judul, ditambahkan_pada) values(1, 'Judul Uji', 0)")
    c.execute("insert into series_sources(id, series_id, adapter, url, peran) values(1, 1, 'komiku', 'https://komiku.org/manga/x/', 'utama')")
    c.execute("insert into chapters(id, series_id, label, label_normal, kunci_urut) values(1, 1, 'Chapter 1', '1', 1)")
    c.execute("insert into chapter_sources values(1, 1, ?)", (URL_CH,))
    ingest.buat_job_unduh(c, 1, 1, 0.0)
    return e


def status(env):
    return env.conn.execute("select status from chapters where id=1").fetchone()[0]


def test_alur_sukses_tmp_terhapus(env):
    asyncio.run(ingest.proses_chapter(*env.args(1)))
    assert status(env) == "siap" and not (env.s.dir_tmp / "1").exists()
    arsip = env.conn.execute("select * from archives").fetchone()
    assert arsip["md5"] == env.drive.berkas(arsip["drive_file_id"]).md5 and arsip["jumlah_gambar"] == 3
    assert json.loads(arsip["manifest"])["gambar"][1]["mime"] == "image/jpeg"
    assert env.conn.execute("select status from jobs where id=1").fetchone()[0] == "selesai"
    assert env.drive.berkas(arsip["drive_file_id"]).nama == "ch-1.cbz"


def test_satu_gambar_rusak_tidak_ada_unggahan(env):
    env.gambar[1] = b"<html>"
    with pytest.raises(GambarRusak):
        asyncio.run(ingest.proses_chapter(*env.args(1)))
    assert env.drive.jumlah() == 0 and status(env) != "siap"
    assert not (env.s.dir_tmp / "1").exists()


def test_unggah_gagal_cbz_tetap_di_tmp(env):
    env.drive.gagal_unggah = DriveError("sementara", "x")
    with pytest.raises(DriveError):
        asyncio.run(ingest.proses_chapter(*env.args(1)))
    assert (env.s.dir_tmp / "1" / "ch.cbz").exists() and status(env) == "mengunggah"


def test_mati_setelah_unggah_tanpa_duplikat(env, monkeypatch):
    asli = ingest._simpan_arsip

    def mati(*a, **kw):
        raise RuntimeError("listrik padam")

    monkeypatch.setattr(ingest, "_simpan_arsip", mati)
    with pytest.raises(RuntimeError):
        asyncio.run(ingest.proses_chapter(*env.args(1)))
    monkeypatch.setattr(ingest, "_simpan_arsip", asli)
    asyncio.run(ingest.proses_chapter(*env.args(1)))
    assert env.drive.jumlah() == 1 and status(env) == "siap"


def test_gambar_rusak_membatalkan_unduhan_lain(env):
    dilayani = []

    async def handler(request):
        if str(request.url) == URL_CH:
            return httpx.Response(200, text=HTML)
        n = int(request.url.path.strip("/").split(".")[0])
        if n == 0:
            return httpx.Response(200, content=b"<html>")
        await asyncio.sleep(0.2)
        dilayani.append(n)
        return httpx.Response(200, content=env.gambar[n])

    env.p = PengambilAman(httpx.AsyncClient(transport=httpx.MockTransport(handler)), resolver=lambda h: ["93.184.216.34"])

    async def jalan():
        with pytest.raises(GambarRusak):
            await ingest.proses_chapter(*env.args(1))
        await asyncio.sleep(0.4)

    asyncio.run(jalan())
    assert dilayani == []


def test_checkpoint_progres_gambar(env):
    asyncio.run(ingest.proses_chapter(*env.args(1)))
    cp = json.loads(env.conn.execute("select checkpoint from jobs where id=1").fetchone()[0])
    assert cp["gambar_total"] == 3 and cp["gambar_selesai"] == 3


def test_chapter_sudah_siap_tidak_diproses_ulang(env):
    asyncio.run(ingest.proses_chapter(*env.args(1)))
    env.conn.execute("update jobs set status='berjalan'")
    env.gambar[0] = b"<html>"  # kalau diunduh ulang, pasti gagal
    asyncio.run(ingest.proses_chapter(*env.args(1)))
    assert env.drive.jumlah() == 1 and status(env) == "siap"
    assert env.conn.execute("select status from jobs where id=1").fetchone()[0] == "selesai"
