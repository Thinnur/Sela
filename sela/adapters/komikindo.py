from urllib.parse import urljoin, urlsplit

from sela.adapters.base import ChapterRef, Judul, pisah_alias, sup, tanpa_awalan_komik, teks, unik_absolut
from sela.fetch import PengambilAman, SumberError

HOST = "komikindo.ch"


class KomikIndo:
    nama = "komikindo"

    def cocok(self, url: str) -> bool:
        b = urlsplit(url)
        return (b.hostname or "").removeprefix("www.") == HOST and b.path.startswith("/komik/")

    def normalisasi(self, url: str) -> str:
        if not self.cocok(url):
            raise SumberError("tidak_didukung", "bukan link halaman judul KomikIndo")
        return self.url_dari_slug(self.slug(url))

    def slug(self, url_kanonis: str) -> str:
        bagian = [b for b in urlsplit(url_kanonis).path.split("/") if b]
        if len(bagian) < 2:
            raise SumberError("tidak_didukung", "slug judul tidak ditemukan")
        return bagian[1]

    def url_dari_slug(self, slug: str) -> str:
        return f"https://{HOST}/komik/{slug}/"

    def parse_judul(self, html: str, url: str) -> Judul:
        s = sup(html)
        info = {}
        for span in s.select(".spe span"):
            kunci, _, nilai = teks(span).partition(":")
            if nilai:
                info[kunci.strip().lower()] = nilai.strip()
        judul = tanpa_awalan_komik(teks(s.select_one("h1.entry-title, h1")))
        tautan = s.select("#chapter_list li .lchx a[href]")
        if not judul or not tautan:
            raise SumberError("berubah", "struktur halaman judul KomikIndo berubah")
        chapters = []
        for a in reversed(tautan):
            tgl = a.find_parent("li").select_one(".dt")
            chapters.append(ChapterRef(teks(a), urljoin(url, a["href"]), teks(tgl) or None))
        sampul = s.select_one(".thumb img")
        return Judul(
            judul=judul,
            alias=pisah_alias(info.get("judul alternatif", "")),
            sinopsis=teks(s.select_one(".entry-content.entry-content-single, .entry-content")),
            sampul_url=urljoin(url, sampul["src"]) if sampul and sampul.get("src") else None,
            jenis=(info.get("jenis komik") or "").lower() or None,
            chapters=chapters,
        )

    def parse_gambar(self, html: str, url_chapter: str) -> list[str]:
        urls = unik_absolut([i.get("src") for i in sup(html).select("#chimg-auh img")], url_chapter)
        if not urls:
            raise SumberError("berubah", "gambar chapter KomikIndo tidak ditemukan")
        return urls

    async def ambil_judul(self, p: PengambilAman, url: str) -> Judul:
        url = self.normalisasi(url)
        return self.parse_judul((await p.ambil(url)).text, url)

    async def ambil_gambar(self, p: PengambilAman, url_chapter: str) -> list[str]:
        urls = self.parse_gambar((await p.ambil(url_chapter)).text, url_chapter)
        # host CDN KomikIndo berganti-ganti: hanya host yang muncul di halaman chapter resmi yang diizinkan
        for host in {urlsplit(u).hostname for u in urls}:
            if host:
                p.izinkan_host(host, self.nama)
        return urls
