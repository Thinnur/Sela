import asyncio
from pathlib import Path

import httpx
import pytest

from sela import db
from sela.adapters.base import ChapterRef, Judul
from sela.fetch import PengambilAman
from sela.ingest import Pratinjau, pratinjau, simpan_sampul, tambahkan
from tests.gambar import webp_bytes

FX = Path(__file__).parent / "fixtures"
URL_KOMIKU = "https://komiku.org/manga/money-keeps-piling-up-no-matter-how-much-i-spend/"
URL_KI = "https://komikindo.ch/komik/money-keeps-piling-up-no-matter-how-much-i-spend/"
HALAMAN = {URL_KOMIKU: FX / "komiku" / "judul.html", URL_KI: FX / "komikindo" / "judul.html"}


def pengambil_fixture():
    def handler(request):
        url = str(request.url)
        if url in HALAMAN:
            return httpx.Response(200, text=HALAMAN[url].read_text(encoding="utf-8"))
        if url.endswith(".webp") or "thumbnail" in url:
            return httpx.Response(200, content=webp_bytes())
        return httpx.Response(404)

    return PengambilAman(httpx.AsyncClient(transport=httpx.MockTransport(handler)), resolver=lambda h: ["93.184.216.34"])


def hitung(conn, sql, *arg):
    return conn.execute(f"select count(*) from {sql}", arg).fetchone()[0]


@pytest.fixture
def pengguna(conn, setelan):
    db.pastikan_pengguna(conn, setelan)
    return 1


def test_pratinjau_menemukan_cadangan(conn):
    pv = asyncio.run(pratinjau(conn, pengambil_fixture(), URL_KOMIKU))
    assert len(pv.judul.chapters) == 27 and pv.cadangan[0] == "komikindo" and len(pv.cadangan[2]) == 26
    assert pv.url == URL_KOMIKU and pv.adapter == "komiku"


def test_tambahkan_membuat_chapter_job_dan_cadangan(conn, pengguna):
    pv = asyncio.run(pratinjau(conn, pengambil_fixture(), URL_KOMIKU))
    sid = tambahkan(conn, pv, user_id=pengguna, tautkan_cadangan=True, jam=1000.0)
    assert hitung(conn, "chapters where series_id=? and status='antre'", sid) == 27
    assert hitung(conn, "jobs where jenis='unduh_chapter' and status='antre'") == 27
    assert hitung(conn, "chapter_sources") == 27 + 26
    assert hitung(conn, "series_sources where peran='cadangan'") == 1
    assert conn.execute("select teks from activity").fetchone()[0].endswith("menambahkan Money Keeps Piling Up No Matter How Much I Spend")
    kunci = [r[0] for r in conn.execute("select kunci_urut from chapters order by kunci_urut")]
    assert kunci[:3] == [1.0, 2.0, 3.0]


def test_url_sama_buka_judul_lama(conn, pengguna):
    pv = asyncio.run(pratinjau(conn, pengambil_fixture(), URL_KOMIKU))
    sid = tambahkan(conn, pv, pengguna, False, 1.0)
    assert asyncio.run(pratinjau(conn, pengambil_fixture(), URL_KOMIKU + "?ref=x")) == sid
    assert tambahkan(conn, pv, pengguna, False, 2.0) == sid
    assert hitung(conn, "series") == 1 and hitung(conn, "jobs") == 27


def test_daftar_ganda_jadi_satu(conn, pengguna):
    u5 = "https://komiku.org/x-chapter-5/"
    pv = Pratinjau("komiku", "https://komiku.org/manga/x/",
                   Judul("X", chapters=[ChapterRef("Chapter 5", u5, None), ChapterRef("Ch. 5", u5 + "#komen", None)]), None)
    tambahkan(conn, pv, pengguna, False, 1.0)
    assert hitung(conn, "chapters") == 1 and hitung(conn, "jobs") == 1


def test_simpan_sampul(tmp_path):
    nama = asyncio.run(simpan_sampul(pengambil_fixture(), "https://thumbnail.komiku.org/a.webp", tmp_path / "7"))
    assert nama == "7.webp" and (tmp_path / "7.webp").exists()
