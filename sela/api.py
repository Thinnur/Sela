import json
import sqlite3
import time
from collections.abc import Iterator

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel

from sela import db, ingest, pembaru, progres
from sela.auth import pengguna_api, wajib_admin
from sela.cache import CachePenuh
from sela.cbz import baca_entri
from sela.drive import DriveError
from sela.fetch import SumberError
from sela.worker import coba_lagi_chapter, coba_lagi_sumber, ukuran_dir

PRIVAT = {"cache-control": "private, max-age=86400"}


class BadanProgres(BaseModel):
    series_id: int
    chapter_id: int
    indeks: int
    fraksi: float
    rev: int


class BadanUrl(BaseModel):
    url: str


class BadanTambah(BaseModel):
    url: str
    tautkan_cadangan: bool = True


class BadanLatar(BaseModel):
    latar: str


class BadanSumber(BaseModel):
    sumber_id: int


def galat(status: int, pesan: str) -> JSONResponse:
    return JSONResponse({"galat": pesan}, status_code=status)


def pasang_api(app: FastAPI) -> None:
    s = app.state.s
    l = app.state.l
    r = APIRouter()

    def koneksi() -> Iterator[sqlite3.Connection]:
        conn = l.buka_db()
        try:
            yield conn
        finally:
            conn.close()

    def arsip(conn: sqlite3.Connection, chapter_id: int) -> sqlite3.Row:
        a = conn.execute("select * from archives where chapter_id=?", (chapter_id,)).fetchone()
        if a is None:
            raise HTTPException(404, detail="chapter belum siap")
        return a

    @r.get("/api/chapter/{chapter_id}/gambar/{n}")
    async def gambar(chapter_id: int, n: int, u=Depends(pengguna_api), conn=Depends(koneksi)):
        a = arsip(conn, chapter_id)
        try:
            path = await l.cache.path(chapter_id, a["drive_file_id"])
        except CachePenuh:
            return galat(503, "Cache baca sedang penuh. Coba lagi sebentar.")
        except DriveError as e:
            return galat(503, f"Drive belum bisa diakses: {e.pesan}")
        try:
            data, mime = baca_entri(path, n)
        except LookupError:
            raise HTTPException(404, detail="gambar tidak ada")
        return Response(data, media_type=mime, headers=PRIVAT)

    @r.post("/api/chapter/{chapter_id}/prefetch-berikut", status_code=204)
    async def prefetch_berikut(chapter_id: int, u=Depends(pengguna_api), conn=Depends(koneksi)):
        b = conn.execute("select a.chapter_id, a.drive_file_id from chapters c join chapters n on n.series_id=c.series_id "
                         "and n.kunci_urut > c.kunci_urut join archives a on a.chapter_id=n.id where c.id=? "
                         "order by n.kunci_urut limit 1", (chapter_id,)).fetchone()
        if b:
            l.cache.prefetch(b["chapter_id"], b["drive_file_id"])

    @r.post("/api/progres")
    def simpan_progres(badan: BadanProgres, u=Depends(pengguna_api), conn=Depends(koneksi)):
        try:
            pos = progres.simpan_posisi(conn, u["id"], badan.series_id, badan.chapter_id, badan.indeks, badan.fraksi, badan.rev)
        except progres.KonflikRev as e:
            return JSONResponse({"posisi": vars(e.sekarang)}, status_code=409)
        except ValueError as e:
            return galat(422, str(e))
        return {"rev": pos.rev}

    @r.post("/api/chapter/{chapter_id}/selesai", status_code=204)
    def selesai(chapter_id: int, u=Depends(pengguna_api), conn=Depends(koneksi)):
        progres.tandai_selesai(conn, u["id"], chapter_id, time.time())

    @r.post("/api/chapter/{chapter_id}/batal-selesai", status_code=204)
    def batal_selesai(chapter_id: int, u=Depends(pengguna_api), conn=Depends(koneksi)):
        progres.batalkan_selesai(conn, u["id"], chapter_id, time.time())

    @r.post("/api/tambah/pratinjau")
    async def tambah_pratinjau(badan: BadanUrl, u=Depends(pengguna_api), conn=Depends(koneksi)):
        try:
            pv = await ingest.pratinjau(conn, l.pengambil, badan.url.strip())
        except SumberError as e:
            return galat(422, e.pesan)
        if isinstance(pv, int):
            return {"series_id": pv}
        cad = {"situs": pembaru.NAMA_SITUS[pv.cadangan[0]], "jumlah": len(pv.cadangan[2])} if pv.cadangan else None
        return {"judul": pv.judul.judul, "sumber": pembaru.NAMA_SITUS[pv.adapter], "jumlah": len(pv.judul.chapters),
                "cadangan": cad}

    @r.post("/api/tambah")
    async def tambah(badan: BadanTambah, u=Depends(pengguna_api), conn=Depends(koneksi)):
        try:
            pv = await ingest.pratinjau(conn, l.pengambil, badan.url.strip())
        except SumberError as e:
            return galat(422, e.pesan)
        if isinstance(pv, int):
            return {"series_id": pv}
        sid = ingest.tambahkan(conn, pv, u["id"], badan.tautkan_cadangan, time.time(), s.interval_cek)
        if pv.judul.sampul_url and not conn.execute("select sampul from series where id=?", (sid,)).fetchone()[0]:
            nama = await ingest.simpan_sampul(l.pengambil, pv.judul.sampul_url, s.dir_data / "sampul" / str(sid))
            conn.execute("update series set sampul=? where id=?", (nama, sid))
        return {"series_id": sid}

    @r.post("/api/chapter/{chapter_id}/coba-lagi", status_code=204)
    def coba_lagi(chapter_id: int, u=Depends(pengguna_api), conn=Depends(koneksi)):
        coba_lagi_chapter(conn, chapter_id)

    @r.post("/api/chapter/{chapter_id}/ambil-cadangan", status_code=202)
    def ambil_cadangan(chapter_id: int, u=Depends(pengguna_api), conn=Depends(koneksi)):
        try:
            pembaru.ambil_dari_cadangan(conn, chapter_id)
        except LookupError as e:
            return galat(404, str(e))
        return {}

    @r.post("/api/series/{series_id}/cek")
    def cek_manual(series_id: int, u=Depends(pengguna_api), conn=Depends(koneksi)):
        return {"diterima": pembaru.minta_cek_manual(conn, series_id, time.time(), s.cooldown_cek_manual)}

    @r.post("/api/sumber/{sumber_id}/coba-lagi", status_code=204)
    def sumber_coba_lagi(sumber_id: int, u=Depends(pengguna_api), conn=Depends(koneksi)):
        coba_lagi_sumber(conn, sumber_id)

    @r.post("/api/series/{series_id}/cadangan")
    async def cadangan(series_id: int, badan: BadanUrl, u=Depends(pengguna_api), conn=Depends(koneksi)):
        try:
            return {"sumber_id": await pembaru.tautkan_cadangan(conn, l.pengambil, series_id, badan.url.strip(), time.time())}
        except (ValueError, SumberError) as e:
            return galat(422, getattr(e, "pesan", str(e)))

    @r.post("/api/series/{series_id}/sumber-utama", status_code=204)
    def sumber_utama(series_id: int, badan: BadanSumber, u=Depends(pengguna_api), conn=Depends(koneksi)):
        wajib_admin(u)
        try:
            pembaru.ganti_sumber_utama(conn, series_id, badan.sumber_id)
        except LookupError as e:
            return galat(404, str(e))

    @r.get("/api/aktivitas")
    def aktivitas(u=Depends(pengguna_api), conn=Depends(koneksi)):
        kejadian = [dict(x) for x in conn.execute(
            "select pada, jenis, teks, series_id, chapter_id from activity order by id desc limit 30")]
        berjalan = []
        for j in conn.execute("select j.checkpoint, c.id, c.label, c.status, s.judul from jobs j join chapters c on c.id=j.target "
                              "join series s on s.id=c.series_id where j.status='berjalan'"):
            cp = json.loads(j["checkpoint"])
            berjalan.append({"chapter_id": j["id"], "label": j["label"], "judul": j["judul"], "status": j["status"],
                             "gambar_selesai": cp.get("gambar_selesai", 0), "gambar_total": cp.get("gambar_total", 0)})
        sumber = [dict(x) for x in conn.execute(
            "select ss.id, ss.adapter, ss.peran, ss.jenis_error, ss.pesan_error, ss.cek_sukses_terakhir, s.judul "
            "from series_sources ss join series s on s.id=ss.series_id")]
        return {"aktivitas": kejadian, "berjalan": berjalan, "sumber": sumber,
                "drive_status": db.kv_ambil(conn, "drive_status") or "tersambung",
                "antrean_jeda": db.kv_ambil(conn, "antrean_jeda") == "1",
                "disk": {"terpakai": ukuran_dir(s.dir_tmp) + ukuran_dir(s.dir_cache), "anggaran": s.anggaran_disk}}

    @r.post("/api/antrean/jeda", status_code=204)
    def jeda(u=Depends(pengguna_api), conn=Depends(koneksi)):
        db.kv_set(conn, "antrean_jeda", "1")

    @r.post("/api/antrean/lanjut", status_code=204)
    def lanjut(u=Depends(pengguna_api), conn=Depends(koneksi)):
        db.kv_set(conn, "antrean_jeda", None)

    @r.post("/api/akun/latar", status_code=204)
    def latar(badan: BadanLatar, u=Depends(pengguna_api), conn=Depends(koneksi)):
        try:
            progres.set_latar(conn, u["id"], badan.latar)
        except ValueError as e:
            return galat(422, str(e))

    @r.get("/sampul/{series_id}")
    def sampul(series_id: int, u=Depends(pengguna_api), conn=Depends(koneksi)):
        row = conn.execute("select sampul from series where id=?", (series_id,)).fetchone()
        path = s.dir_data / "sampul" / row["sampul"] if row and row["sampul"] else None
        if path is None or not path.is_file():
            raise HTTPException(404, detail="sampul tidak ada")
        return FileResponse(path, headers=PRIVAT)

    app.include_router(r)
