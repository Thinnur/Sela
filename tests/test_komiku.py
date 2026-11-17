import asyncio
import json
from pathlib import Path

import httpx

from sela.adapters import adapter_untuk
from sela.adapters.komiku import Komiku
from sela.fetch import PengambilAman
from sela.urutan import normalisasi_label

FX = Path(__file__).parent / "fixtures" / "komiku"
URL_JUDUL = "https://komiku.org/manga/money-keeps-piling-up-no-matter-how-much-i-spend/"
URL_CH1 = "https://komiku.org/money-keeps-piling-up-no-matter-how-much-i-spend-chapter-1/"
URL_PANJANG = "https://komiku.org/manga/black-clover-indonesia/"


def baca(nama):
    return (FX / nama).read_text(encoding="utf-8")


def test_parse_gambar_sama_dengan_manifest_hermes():
    urls = Komiku().parse_gambar(baca("chapter-1.html"), URL_CH1)
    assert urls == json.loads(baca("chapter-1-urls.json")) and len(urls) == 146
    assert urls[0] == "https://img.komiku.org/upload5/money-keeps-piling-up-no-matter-how/1/2026-06-19/1_part1.jpg"


def test_parse_judul():
    j = Komiku().parse_judul(baca("judul.html"), URL_JUDUL)
    assert j.judul == "Money Keeps Piling Up No Matter How Much I Spend"
    assert len(j.chapters) == 27
    assert [normalisasi_label(c.label) for c in j.chapters][:3] == ["1", "2", "3"]
    assert all(c.url.startswith("https://komiku.org/") for c in j.chapters)
    assert j.sampul_url.startswith("https://thumbnail.komiku.org/")
    assert j.jenis == "manhua" and "Ketika seorang mahasiswa" in j.sinopsis and "<" not in j.sinopsis


def test_judul_panjang_lengkap_tanpa_duplikat():
    ch = Komiku().parse_judul(baca("judul-panjang.html"), URL_PANJANG).chapters
    assert len(ch) > 100 and len({c.url for c in ch}) == len(ch)
    assert normalisasi_label(ch[0].label) == "1" and normalisasi_label(ch[-1].label) == "393"


def test_slug_bolak_balik():
    k = Komiku()
    assert k.url_dari_slug(k.slug(URL_JUDUL)) == URL_JUDUL
    assert k.normalisasi(URL_JUDUL.rstrip("/") + "?ref=x#a") == URL_JUDUL
    assert adapter_untuk("https://komiku.org/manga/x/").nama == "komiku"


def test_ambil_judul_lewat_pengambil():
    def handler(request):
        return httpx.Response(200, text=baca("judul.html"))

    p = PengambilAman(httpx.AsyncClient(transport=httpx.MockTransport(handler)), resolver=lambda h: ["93.184.216.34"])
    assert len(asyncio.run(Komiku().ambil_judul(p, URL_JUDUL)).chapters) == 27
