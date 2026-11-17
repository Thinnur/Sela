from urllib.parse import urljoin, urlsplit

from sela.adapters.base import ChapterRef, Judul, pisah_alias, sup, tanpa_awalan_komik, teks, unik_absolut
from sela.fetch import PengambilAman, SumberError

HOST = "komiku.org"


class Komiku:
    nama = "komiku"

    def cocok(self, url: str) -> bool:
        b = urlsplit(url)
        return (b.hostname or "").removeprefix("www.") == HOST and b.path.startswith("/manga/")

    def normalisasi(self, url: str) -> str:
        if not self.cocok(url):
            raise SumberError("tidak_didukung", "bukan link halaman judul Komiku")
        return self.url_dari_slug(self.slug(url))

    def slug(self, url_kanonis: str) -> str:
        bagian = [b for b in urlsplit(url_kanonis).path.split("/") if b]
        if len(bagian) < 2:
            raise SumberError("tidak_didukung", "slug judul tidak ditemukan")
        return bagian[1]

    def url_dari_slug(self, slug: str) -> str:
        return f"https://{HOST}/manga/{slug}/"

    def parse_judul(self, html: str, url: str) -> Judul:
        s = sup(html)
        info = {}
        for baris in s.select("table.inftable tr"):
            sel = baris.find_all("td")
            if len(sel) >= 2:
                info[teks(sel[0]).rstrip(":").lower()] = teks(sel[1])
        judul = info.get("judul") or tanpa_awalan_komik(teks(s.select_one("#Judul h1, h1")))
        tautan = s.select("#Daftar_Chapter td.judulseries a[href]")
        if not judul or not tautan:
            raise SumberError("berubah", "struktur halaman judul Komiku berubah")
        chapters = []
        for a in reversed(tautan):
            tgl = a.find_parent("tr").select_one("td.tanggalseries")
            chapters.append(ChapterRef(teks(a), urljoin(url, a["href"]), teks(tgl) or None))
        sampul = s.select_one("img[itemprop=image]")
        return Judul(
            judul=judul,
            alias=pisah_alias(info.get("judul alternatif", "")),
            sinopsis=teks(s.select_one("#Sinopsis .desc, .desc")),
            sampul_url=urljoin(url, sampul["src"]) if sampul and sampul.get("src") else None,
            jenis=(info.get("tipe") or "").lower() or None,
            chapters=chapters,
        )

    def parse_gambar(self, html: str, url_chapter: str) -> list[str]:
        imgs = sup(html).select("#Baca_Komik img")
        urls = unik_absolut([i.get("data-src") or i.get("src") for i in imgs], url_chapter)
        if not urls:
            raise SumberError("berubah", "gambar chapter Komiku tidak ditemukan")
        return urls

    async def ambil_judul(self, p: PengambilAman, url: str) -> Judul:
        url = self.normalisasi(url)
        return self.parse_judul((await p.ambil(url)).text, url)

    async def ambil_gambar(self, p: PengambilAman, url_chapter: str) -> list[str]:
        return self.parse_gambar((await p.ambil(url_chapter)).text, url_chapter)
