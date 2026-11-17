import re
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from sela.fetch import PengambilAman


@dataclass(frozen=True)
class ChapterRef:
    label: str
    url: str
    terbit: str | None


@dataclass(frozen=True)
class Judul:
    judul: str
    alias: list[str] = field(default_factory=list)
    sinopsis: str = ""
    sampul_url: str | None = None
    jenis: str | None = None
    chapters: list[ChapterRef] = field(default_factory=list)


class Adapter(Protocol):
    nama: str

    def cocok(self, url: str) -> bool: ...
    def normalisasi(self, url: str) -> str: ...
    def slug(self, url_kanonis: str) -> str: ...
    def url_dari_slug(self, slug: str) -> str: ...
    def parse_judul(self, html: str, url: str) -> Judul: ...
    def parse_gambar(self, html: str, url_chapter: str) -> list[str]: ...
    async def ambil_judul(self, p: PengambilAman, url: str) -> Judul: ...
    async def ambil_gambar(self, p: PengambilAman, url_chapter: str) -> list[str]: ...


def sup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def teks(node) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip() if node else ""


def tanpa_awalan_komik(judul: str) -> str:
    return re.sub(r"^komik\s+", "", judul, flags=re.I).strip()


def pisah_alias(nilai: str) -> list[str]:
    return [a.strip() for a in re.split(r"[,;]", nilai) if a.strip()]


def unik_absolut(urls: list[str | None], dasar: str) -> list[str]:
    hasil, lihat = [], set()
    for u in urls:
        if not u:
            continue
        u = urljoin(dasar, u.strip())
        if u.startswith("https://") and u not in lihat:
            lihat.add(u)
            hasil.append(u)
    return hasil
