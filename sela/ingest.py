import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from sela import db
from sela.adapters import ADAPTER, adapter_untuk
from sela.adapters.base import ChapterRef, Judul
from sela.cbz import periksa_gambar
from sela.fetch import PengambilAman, SumberError
from sela.urutan import kunci_urut_semua, normalisasi_label

INTERVAL_BAWAAN = 21600


@dataclass(frozen=True)
class Pratinjau:
    adapter: str
    url: str
    judul: Judul
    cadangan: tuple[str, str, list[ChapterRef]] | None


def _series_dari_url(conn: sqlite3.Connection, url: str) -> int | None:
    r = conn.execute("select series_id from series_sources where url=?", (url,)).fetchone()
    return r[0] if r else None


async def pratinjau(conn: sqlite3.Connection, p: PengambilAman, url: str) -> Pratinjau | int:
    a = adapter_untuk(url)
    url = a.normalisasi(url)
    ada = _series_dari_url(conn, url)
    if ada is not None:
        return ada
    judul = await a.ambil_judul(p, url)
    cadangan = None
    for nama, lain in ADAPTER.items():
        if nama == a.nama:
            continue
        url_c = lain.url_dari_slug(a.slug(url))
        try:
            cadangan = (nama, url_c, (await lain.ambil_judul(p, url_c)).chapters)
            break
        except SumberError:
            continue  # cadangan tidak wajib
    return Pratinjau(a.nama, url, judul, cadangan)


def _unik_per_label(chapters: list[ChapterRef]) -> list[tuple[str, ChapterRef]]:
    lihat, hasil = set(), []
    for c in chapters:
        ln = normalisasi_label(c.label)
        if ln not in lihat:
            lihat.add(ln)
            hasil.append((ln, c))
    return hasil


def nama_pengguna(conn: sqlite3.Connection, user_id: int) -> str:
    r = conn.execute("select nama, email from users where id=?", (user_id,)).fetchone()
    return (r["nama"] or r["email"].split("@")[0]) if r else "Seseorang"


def catat(conn: sqlite3.Connection, jam: float, jenis: str, teks: str, series_id=None, chapter_id=None, user_id=None):
    conn.execute("insert into activity(pada, jenis, series_id, chapter_id, user_id, teks) values(?,?,?,?,?,?)",
                 (jam, jenis, series_id, chapter_id, user_id, teks))


def buat_job_unduh(conn: sqlite3.Connection, chapter_id: int, sumber_id: int, jam: float) -> int:
    conn.execute("insert into jobs(jenis, target, sumber_id, kunci_idem, dibuat, diperbarui) values('unduh_chapter',?,?,?,?,?) "
                 "on conflict(kunci_idem) do update set status='antre', percobaan=0, jalan_setelah=0, jenis_error=null, "
                 "pesan_error=null, diperbarui=excluded.diperbarui",
                 (chapter_id, sumber_id, f"unduh:{chapter_id}:{sumber_id}", jam, jam))
    return conn.execute("select id from jobs where kunci_idem=?", (f"unduh:{chapter_id}:{sumber_id}",)).fetchone()[0]


def sisipkan_chapter_cadangan(conn: sqlite3.Connection, series_id: int, sumber_id: int, chapters: list[ChapterRef]) -> list[int]:
    """Tautkan chapter cadangan ke chapter yang labelnya sama; label baru jadi 'hanya_cadangan'. Mengembalikan id chapter baru."""
    peta = {r["label_normal"]: r["id"] for r in conn.execute("select id, label_normal from chapters where series_id=?", (series_id,))}
    kunci_maks = conn.execute("select coalesce(max(kunci_urut), 0) from chapters where series_id=?", (series_id,)).fetchone()[0]
    baru = []
    for ln, c in _unik_per_label(chapters):
        if ln not in peta:
            try:
                kunci = float(ln)
            except ValueError:
                kunci = kunci_maks = kunci_maks + 0.001
            peta[ln] = conn.execute("insert into chapters(series_id, label, label_normal, kunci_urut, terbit, status) "
                                    "values(?,?,?,?,?,'hanya_cadangan')", (series_id, c.label, ln, kunci, c.terbit)).lastrowid
            baru.append(peta[ln])
        conn.execute("insert or ignore into chapter_sources(chapter_id, sumber_id, url) values(?,?,?)", (peta[ln], sumber_id, c.url))
    return baru


def tambahkan(conn: sqlite3.Connection, pv: Pratinjau, user_id: int, tautkan_cadangan: bool, jam: float,
              interval: int = INTERVAL_BAWAAN) -> int:
    with db.transaksi(conn):
        ada = _series_dari_url(conn, pv.url)
        if ada is not None:
            return ada
        j = pv.judul
        sid = conn.execute("insert into series(judul, alias, sinopsis, jenis, ditambahkan_oleh, ditambahkan_pada) "
                           "values(?,?,?,?,?,?)", (j.judul, json.dumps(j.alias, ensure_ascii=False), j.sinopsis, j.jenis,
                                                   user_id, jam)).lastrowid
        utama = conn.execute("insert into series_sources(series_id, adapter, url, peran, cek_terakhir, cek_sukses_terakhir, "
                             "cek_berikutnya) values(?,?,?,'utama',?,?,?)",
                             (sid, pv.adapter, pv.url, jam, jam, jam + interval)).lastrowid
        unik = _unik_per_label(j.chapters)
        for (ln, c), kunci in zip(unik, kunci_urut_semua([ln for ln, _ in unik])):
            cid = conn.execute("insert into chapters(series_id, label, label_normal, kunci_urut, terbit) values(?,?,?,?,?)",
                               (sid, c.label, ln, kunci, c.terbit)).lastrowid
            conn.execute("insert into chapter_sources(chapter_id, sumber_id, url) values(?,?,?)", (cid, utama, c.url))
            buat_job_unduh(conn, cid, utama, jam)
        if tautkan_cadangan and pv.cadangan:
            nama_c, url_c, chapters_c = pv.cadangan
            cad = conn.execute("insert into series_sources(series_id, adapter, url, peran, cek_terakhir, cek_sukses_terakhir, "
                               "cek_berikutnya) values(?,?,?,'cadangan',?,?,?)",
                               (sid, nama_c, url_c, jam, jam, jam + interval)).lastrowid
            sisipkan_chapter_cadangan(conn, sid, cad, chapters_c)
        catat(conn, jam, "judul_ditambah", f"{nama_pengguna(conn, user_id)} menambahkan {j.judul}", sid, user_id=user_id)
        return sid


async def simpan_sampul(p: PengambilAman, url: str, tujuan_tanpa_ext: Path) -> str | None:
    """Unduh sampul, pastikan benar gambar, simpan sebagai <tujuan>.<ext>. Mengembalikan nama berkasnya."""
    try:
        data = (await p.ambil(url)).content
        info = periksa_gambar(data)
    except Exception:  # sampul tidak wajib; judul tetap bisa ditambahkan
        return None
    tujuan = Path(f"{tujuan_tanpa_ext}.{info.ext}")
    tujuan.parent.mkdir(parents=True, exist_ok=True)
    tujuan.write_bytes(data)
    return tujuan.name
