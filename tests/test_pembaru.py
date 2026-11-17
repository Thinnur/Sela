import asyncio
import random
from pathlib import Path

import httpx
import pytest
from bs4 import BeautifulSoup

from sela import db, ingest, pembaru
from sela.fetch import PengambilAman

FX = Path(__file__).parent / "fixtures"
URL_KOMIKU = "https://komiku.org/manga/money-keeps-piling-up-no-matter-how-much-i-spend/"
URL_KI = "https://komikindo.ch/komik/money-keeps-piling-up-no-matter-how-much-i-spend/"
KOMIKU = (FX / "komiku" / "judul.html").read_text(encoding="utf-8")
KI = (FX / "komikindo" / "judul.html").read_text(encoding="utf-8")


def komiku_tanpa(n_terbaru: int) -> str:
    s = BeautifulSoup(KOMIKU, "html.parser")
    for td in s.select("#Daftar_Chapter td.judulseries")[:n_terbaru]:
        td.find_parent("tr").decompose()
    return str(s)


def komiku_kosong_tengah(n: int) -> str:
    s = BeautifulSoup(KOMIKU, "html.parser")
    for td in s.select("#Daftar_Chapter td.judulseries")[5:5 + n]:
        td.find_parent("tr").decompose()
    return str(s)


def ki_plus_27() -> str:
    s = BeautifulSoup(KI, "html.parser")
    li = s.select_one("#chapter_list li")
    baru = BeautifulSoup(str(li).replace("chapter-26", "chapter-27").replace(">26<", ">27<"), "html.parser")
    li.insert_before(baru)
    return str(s)


class Sumber:
    def __init__(self):
        self.halaman = {URL_KOMIKU: KOMIKU, URL_KI: KI}
        self.status = {}

    def pengambil(self):
        def handler(request):
            url = str(request.url)
            if url in self.status:
                return httpx.Response(self.status[url])
            return httpx.Response(200, text=self.halaman[url])

        return PengambilAman(httpx.AsyncClient(transport=httpx.MockTransport(handler)), resolver=lambda h: ["93.184.216.34"])


@pytest.fixture
def sumber():
    return Sumber()


@pytest.fixture
def judul(conn, setelan, sumber):
    """Judul dengan 26 chapter dari Komiku dan cadangan KomikIndo (26)."""
    db.pastikan_pengguna(conn, setelan)
    sumber.halaman[URL_KOMIKU] = komiku_tanpa(1)
    pv = asyncio.run(ingest.pratinjau(conn, sumber.pengambil(), URL_KOMIKU))
    sid = ingest.tambahkan(conn, pv, 1, True, 1000.0)
    sumber.halaman[URL_KOMIKU] = KOMIKU
    return sid


def id_sumber(conn, peran):
    return conn.execute("select id from series_sources where peran=?", (peran,)).fetchone()[0]


def hitung(conn, sql, *arg):
    return conn.execute(f"select count(*) from {sql}", arg).fetchone()[0]


def test_chapter_baru_tepat_satu_job(conn, judul, sumber):
    utama = id_sumber(conn, "utama")
    assert asyncio.run(pembaru.cek_sumber(conn, sumber.pengambil(), utama, 2000.0)) == pembaru.HasilCek(1, None)
    assert asyncio.run(pembaru.cek_sumber(conn, sumber.pengambil(), utama, 3000.0)) == pembaru.HasilCek(0, None)
    assert hitung(conn, "jobs where jenis='unduh_chapter'") == 27
    assert conn.execute("select teks from activity order by id desc").fetchone()[0] == "Chapter 27 terbit di Komiku"
    assert conn.execute("select cek_sukses_terakhir from series_sources where id=?", (utama,)).fetchone()[0] == 3000.0


def test_daftar_kosong_anomali_tanpa_hapus(conn, judul, sumber):
    utama = id_sumber(conn, "utama")
    sumber.halaman[URL_KOMIKU] = "<html><body>kosong</body></html>"
    hasil = asyncio.run(pembaru.cek_sumber(conn, sumber.pengambil(), utama, 2000.0))
    assert hasil.baru == 0 and hasil.anomali
    r = conn.execute("select jenis_error, cek_sukses_terakhir from series_sources where id=?", (utama,)).fetchone()
    assert tuple(r) == ("berubah", 1000.0) and hitung(conn, "chapters") == 26


def test_hilang_tiga_anomali(conn, judul, sumber):
    utama = id_sumber(conn, "utama")
    sumber.halaman[URL_KOMIKU] = komiku_kosong_tengah(3)
    assert asyncio.run(pembaru.cek_sumber(conn, sumber.pengambil(), utama, 2000.0)).anomali
    assert hitung(conn, "chapters") == 26 and hitung(conn, "chapter_sources") == 52


def test_hilang_dua_masih_wajar(conn, judul, sumber):
    sumber.halaman[URL_KOMIKU] = komiku_kosong_tengah(2)
    assert asyncio.run(pembaru.cek_sumber(conn, sumber.pengambil(), id_sumber(conn, "utama"), 2000.0)).anomali is None


def test_utama_gagal_cadangan_dicek(conn, setelan, judul, sumber):
    sumber.status[URL_KOMIKU] = 503
    sumber.halaman[URL_KI] = ki_plus_27()
    sehat = asyncio.run(pembaru.detak(conn, sumber.pengambil(), setelan, 1_000_000.0))
    assert sehat == {"komikindo"}
    ch = conn.execute("select id, status from chapters where label_normal='27'").fetchone()
    assert ch["status"] == "hanya_cadangan" and hitung(conn, "jobs where target=?", ch["id"]) == 0
    pembaru.ambil_dari_cadangan(conn, ch["id"])
    assert conn.execute("select sumber_id from jobs where target=?", (ch["id"],)).fetchone()[0] == id_sumber(conn, "cadangan")
    assert conn.execute("select status from chapters where id=?", (ch["id"],)).fetchone()[0] == "antre"


def test_ambil_dari_cadangan_tanpa_sumber(conn, judul):
    cid = conn.execute("insert into chapters(series_id, label, label_normal, kunci_urut) values(?, 'X', '99', 99)", (judul,)).lastrowid
    with pytest.raises(LookupError):
        pembaru.ambil_dari_cadangan(conn, cid)


def test_cek_manual_cooldown(conn, judul):
    assert pembaru.minta_cek_manual(conn, judul, 0.0, 600)
    assert not pembaru.minta_cek_manual(conn, judul, 599.0, 600)
    assert pembaru.minta_cek_manual(conn, judul, 601.0, 600)
    assert conn.execute("select cek_berikutnya from series_sources where peran='utama'").fetchone()[0] == 601.0


def test_jitter(conn, setelan, judul, sumber):
    jam = 1_000_000.0
    asyncio.run(pembaru.detak(conn, sumber.pengambil(), setelan, jam, acak=random.uniform))
    berikut = conn.execute("select cek_berikutnya from series_sources where peran='utama'").fetchone()[0]
    assert 21600 - 1800 <= berikut - jam <= 21600 + 1800


def test_detak_hanya_yang_jatuh_tempo(conn, setelan, judul, sumber):
    sumber.status[URL_KOMIKU] = 500
    assert asyncio.run(pembaru.detak(conn, sumber.pengambil(), setelan, 1001.0)) == set()
    assert conn.execute("select jenis_error from series_sources where peran='utama'").fetchone()[0] is None


def test_tautkan_cadangan_manual(conn, setelan, sumber):
    db.pastikan_pengguna(conn, setelan)
    pv = asyncio.run(ingest.pratinjau(conn, sumber.pengambil(), URL_KOMIKU))
    sid = ingest.tambahkan(conn, pv, 1, False, 1.0)
    cad = asyncio.run(pembaru.tautkan_cadangan(conn, sumber.pengambil(), sid, URL_KI, 2.0))
    assert hitung(conn, "chapter_sources where sumber_id=?", cad) == 26
    with pytest.raises(ValueError):
        asyncio.run(pembaru.tautkan_cadangan(conn, sumber.pengambil(), sid, URL_KOMIKU, 3.0))


def test_ganti_sumber_utama(conn, judul):
    utama, cad = id_sumber(conn, "utama"), id_sumber(conn, "cadangan")
    c1 = conn.execute("select id from chapters where label_normal='1'").fetchone()[0]
    conn.execute("update chapters set status='siap' where id=?", (c1,))
    conn.execute("insert into archives values(?, 'F', ?, 1, 'm', 's', 1, '{}', 0)", (c1, utama))
    conn.execute("update jobs set status='selesai' where target=?", (c1,))
    pembaru.ganti_sumber_utama(conn, judul, cad)
    assert id_sumber(conn, "utama") == cad and id_sumber(conn, "cadangan") == utama
    assert hitung(conn, "jobs where sumber_id=? and status='antre'", utama) == 0
    assert hitung(conn, "jobs where sumber_id=? and status='antre'", cad) == 25
    assert conn.execute("select drive_file_id from archives where chapter_id=?", (c1,)).fetchone()[0] == "F"
