import asyncio
import json
from pathlib import Path

import httpx

from sela.adapters import adapter_untuk
from sela.adapters.komikindo import KomikIndo
from sela.fetch import PengambilAman

FX = Path(__file__).parent / "fixtures" / "komikindo"
URL_JUDUL = "https://komikindo.ch/komik/money-keeps-piling-up-no-matter-how-much-i-spend/"
URL_CH1 = "https://komikindo.ch/money-keeps-piling-up-no-matter-how-much-i-spend-chapter-1/"


def baca(nama):
    return (FX / nama).read_text(encoding="utf-8")


def test_parse_gambar_utuh_dengan_query():
    urls = KomikIndo().parse_gambar(baca("chapter-1.html"), URL_CH1)
    assert urls == json.loads(baca("chapter-1-urls.json")) and len(urls) == 79
    assert urls[-1].endswith("GfWnZEzIP4skLTZlGCZarbwQ1lkkoijCiTFguP12.jpeg?mi_revision=2&mi_delivery=1")


def test_ambil_gambar_mendaftarkan_lima_host():
    terdaftar = set()

    class Pengambil(PengambilAman):
        def izinkan_host(self, host, situs):
            assert situs == "komikindo"
            terdaftar.add(host)
            super().izinkan_host(host, situs)

    p = Pengambil(httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=baca("chapter-1.html")))),
                  resolver=lambda h: ["93.184.216.34"])
    urls = asyncio.run(KomikIndo().ambil_gambar(p, URL_CH1))
    assert len(urls) == 79
    assert terdaftar == {"amatipolanyatirudesainnya.lol", "bukansiapasiapa.lol", "ss.guatauaslinyalusiapa.asia",
                         "ss.menjadimanusiaikan.asia", "ss.rasainginberak.asia"}
    assert p.situs_dari(urls[0]) == "komikindo"


def test_parse_judul_dan_slug():
    j = KomikIndo().parse_judul(baca("judul.html"), URL_JUDUL)
    assert j.judul == "Money Keeps Piling Up No Matter How Much I Spend"
    assert len(j.chapters) == 26 and j.chapters[0].label.endswith("1") and j.chapters[-1].label.endswith("26")
    assert j.jenis == "manhwa" and j.sampul_url.startswith("https://komikindo.ch/")
    assert KomikIndo().url_dari_slug("money-keeps-piling-up-no-matter-how-much-i-spend") == URL_JUDUL
    assert adapter_untuk(URL_JUDUL).nama == "komikindo"
