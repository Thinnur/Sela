import asyncio
import json
import logging
import re
import shutil
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urldefrag, urlsplit

from sela import db
from sela.adapters import ADAPTER, adapter_untuk
from sela.adapters.base import ChapterRef, Judul
from sela.cbz import GambarRusak, HasilCbz, buat_cbz, hasil_dari, periksa_gambar
from sela.drive import BerkasDrive, Drive, DriveError
from sela.fetch import PengambilAman, SumberError
from sela.setelan import Setelan
from sela.urutan import kunci_urut_semua, normalisasi_label

INTERVAL_BAWAAN = 21600
MAKS_GAMBAR = 600
log = logging.getLogger("sela.ingest")


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
    """Satu entri per label dan per URL (tanpa #fragmen); entri pertama yang menang."""
    label_ada, url_ada, hasil = set(), set(), []
    for c in chapters:
        ln, url = normalisasi_label(c.label), urldefrag(c.url).url
        if ln in label_ada or url in url_ada:
            continue
        label_ada.add(ln)
        url_ada.add(url)
        hasil.append((ln, ChapterRef(c.label, url, c.terbit)))
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


def pastikan_chapter(conn: sqlite3.Connection, series_id: int, sumber_id: int, ln: str, c: ChapterRef,
                     status: str) -> tuple[int, bool]:
    """Cari chapter berlabel ln atau buat baru dengan status ini, lalu tautkan ke sumber. Mengembalikan (id, baru_dibuat)."""
    r = conn.execute("select id from chapters where series_id=? and label_normal=?", (series_id, ln)).fetchone()
    dibuat = r is None
    if dibuat:
        try:
            kunci = float(ln)
        except ValueError:
            kunci = conn.execute("select coalesce(max(kunci_urut), 0) + 0.001 from chapters where series_id=?",
                                 (series_id,)).fetchone()[0]
        cid = conn.execute("insert into chapters(series_id, label, label_normal, kunci_urut, terbit, status) values(?,?,?,?,?,?)",
                           (series_id, c.label, ln, kunci, c.terbit, status)).lastrowid
    else:
        cid = r[0]
    conn.execute("insert or ignore into chapter_sources(chapter_id, sumber_id, url) values(?,?,?)", (cid, sumber_id, c.url))
    return cid, dibuat


def sisipkan_chapter_cadangan(conn: sqlite3.Connection, series_id: int, sumber_id: int, chapters: list[ChapterRef]) -> list[int]:
    """Tautkan chapter cadangan ke chapter yang labelnya sama; label baru jadi 'hanya_cadangan'. Mengembalikan id chapter baru."""
    return [cid for ln, c in _unik_per_label(chapters)
            for cid, dibuat in [pastikan_chapter(conn, series_id, sumber_id, ln, c, "hanya_cadangan")] if dibuat]


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


def _status(conn: sqlite3.Connection, chapter_id: int, status: str, pesan: str | None = None) -> None:
    conn.execute("update chapters set status=?, pesan_status=? where id=?", (status, pesan, chapter_id))


def _checkpoint(conn: sqlite3.Connection, job_id: int, **isi) -> None:
    cp = json.loads(conn.execute("select checkpoint from jobs where id=?", (job_id,)).fetchone()[0])
    cp.update(isi)
    conn.execute("update jobs set checkpoint=? where id=?", (json.dumps(cp), job_id))


def _nama_aman(label_normal: str) -> str:
    return re.sub(r"[^0-9a-z.]+", "-", label_normal.lower()).strip("-") or "x"


async def _folder_judul(conn: sqlite3.Connection, drive: Drive, s: Setelan, series: sqlite3.Row) -> str:
    sid = series["id"]
    folder = db.kv_ambil(conn, f"folder:{sid}")
    if folder:
        return folder
    akar = db.kv_ambil(conn, "folder:akar")
    if not akar:
        akar = await drive.pastikan_folder("Sela", None)
        db.kv_set(conn, "folder:akar", akar)
    folder = await drive.pastikan_folder(f"{series['judul']} [{sid}]", akar)
    db.kv_set(conn, f"folder:{sid}", folder)
    if series["sampul"] and not db.kv_ambil(conn, f"sampul:{sid}"):
        sampul = s.dir_data / "sampul" / series["sampul"]
        if sampul.exists():
            await drive.unggah(sampul, f"sampul{sampul.suffix}", folder, {"sela_sampul": str(sid)})
            db.kv_set(conn, f"sampul:{sid}", "1")
    return folder


async def _unduh_gambar(conn, p: PengambilAman, adapter, url_chapter: str, kerja: Path, job_id: int):
    urls = await adapter.ambil_gambar(p, url_chapter)
    if len(urls) > MAKS_GAMBAR:
        raise SumberError("berubah", f"jumlah gambar tidak wajar ({len(urls)})")
    raw = kerja / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    selesai = 0
    _checkpoint(conn, job_id, tahap="unduh", gambar_selesai=0, gambar_total=len(urls))

    async def satu(n: int, url: str):
        nonlocal selesai
        data = (await p.ambil(url, referer=url_chapter)).content
        try:
            info = await asyncio.to_thread(periksa_gambar, data)
        except GambarRusak as e:
            raise GambarRusak(f"gambar ke-{n} rusak") from e
        path = raw / f"{n:04d}"
        path.write_bytes(data)
        selesai += 1
        if selesai % 10 == 0 or selesai == len(urls):
            _checkpoint(conn, job_id, gambar_selesai=selesai)
        return path, info, urlsplit(url).hostname or ""

    tugas = [asyncio.ensure_future(satu(n, u)) for n, u in enumerate(urls, 1)]
    try:
        return await asyncio.gather(*tugas)
    except BaseException:
        for t in tugas:
            t.cancel()  # satu gambar gagal: chapter pasti tidak lengkap, hentikan unduhan sisanya
        await asyncio.gather(*tugas, return_exceptions=True)
        raise


def _simpan_arsip(conn: sqlite3.Connection, chapter: sqlite3.Row, job_id: int, sumber_id: int, berkas: BerkasDrive,
                  hasil: HasilCbz, jam: float) -> None:
    with db.transaksi(conn):
        conn.execute("insert or replace into archives values(?,?,?,?,?,?,?,?,?)",
                     (chapter["id"], berkas.id, sumber_id, hasil.ukuran, hasil.md5, hasil.sha256, hasil.jumlah,
                      json.dumps(hasil.manifest, ensure_ascii=False), jam))
        conn.execute("update chapters set status='siap', pesan_status=null, siap_pada=? where id=?", (jam, chapter["id"]))
        conn.execute("update jobs set status='selesai', jenis_error=null, pesan_error=null, diperbarui=? where id=?", (jam, job_id))
        catat(conn, jam, "chapter_siap", f"{chapter['label']} siap dibaca", chapter["series_id"], chapter["id"])


async def proses_chapter(buka_db: Callable[[], sqlite3.Connection], p: PengambilAman, drive: Drive, s: Setelan,
                         job_id: int) -> None:
    conn = buka_db()
    try:
        job = conn.execute("select * from jobs where id=?", (job_id,)).fetchone()
        if conn.execute("select 1 from archives where chapter_id=?", (job["target"],)).fetchone():
            conn.execute("update jobs set status='selesai', diperbarui=? where id=?", (time.time(), job_id))
            return  # chapter sudah siap lewat job lain; jangan unduh ulang atau ganti sumbernya
        chapter = conn.execute("select * from chapters where id=?", (job["target"],)).fetchone()
        sumber = conn.execute("select * from series_sources where id=?", (job["sumber_id"],)).fetchone()
        series = conn.execute("select * from series where id=?", (chapter["series_id"],)).fetchone()
        url_chapter = conn.execute("select url from chapter_sources where chapter_id=? and sumber_id=?",
                                   (chapter["id"], sumber["id"])).fetchone()["url"]
        kerja = s.dir_tmp / str(job_id)
        cbz = kerja / "ch.cbz"

        if not cbz.exists():
            _status(conn, chapter["id"], "mengunduh")
            try:
                berkas = await _unduh_gambar(conn, p, ADAPTER[sumber["adapter"]], url_chapter, kerja, job_id)
                sementara = kerja / "ch.cbz.part"
                await asyncio.to_thread(buat_cbz, sementara, berkas,
                                        {"adapter": sumber["adapter"], "url_chapter": url_chapter, "label": chapter["label"]})
                sementara.rename(cbz)  # ch.cbz hanya ada kalau arsipnya lengkap
            except BaseException:
                shutil.rmtree(kerja, ignore_errors=True)
                raise
            shutil.rmtree(kerja / "raw", ignore_errors=True)
        hasil = await asyncio.to_thread(hasil_dari, cbz)

        _status(conn, chapter["id"], "mengunggah")
        _checkpoint(conn, job_id, tahap="unggah")
        folder = await _folder_judul(conn, drive, s, series)
        ada = await drive.cari({"sela_chapter": str(chapter["id"])})
        cocok = [b for b in ada if b.md5 == hasil.md5]
        if ada and not cocok:
            log.warning("chapter %s punya arsip lama di Drive dengan isi berbeda; arsip lama dibiarkan", chapter["id"])
        berkas_drive = cocok[0] if cocok else await drive.unggah(
            cbz, f"ch-{_nama_aman(chapter['label_normal'])}.cbz", folder,
            {"sela_chapter": str(chapter["id"]), "sela_job": str(job_id)})

        _status(conn, chapter["id"], "memverifikasi")
        _checkpoint(conn, job_id, tahap="verifikasi")
        if berkas_drive.ukuran != hasil.ukuran or berkas_drive.md5 != hasil.md5:
            raise DriveError("sementara", "isi di Drive tidak cocok dengan arsip lokal")
        _simpan_arsip(conn, chapter, job_id, sumber["id"], berkas_drive, hasil, time.time())
        shutil.rmtree(kerja, ignore_errors=True)
    finally:
        conn.close()


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
