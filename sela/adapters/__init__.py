from sela.adapters.base import Adapter
from sela.adapters.komiku import Komiku
from sela.fetch import SumberError

ADAPTER: dict[str, Adapter] = {"komiku": Komiku()}


def adapter_untuk(url: str) -> Adapter:
    for a in ADAPTER.values():
        if a.cocok(url):
            return a
    raise SumberError("tidak_didukung", "situs ini belum didukung. Pakai link halaman judul Komiku atau KomikIndo.")
