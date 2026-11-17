import json
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from sela import db, progres, tampilan
from sela.api import pasang_api
from sela.auth import butuh_sesi, pasang_rute_auth, pengguna_html, respons_tanpa_sesi
from sela.pembaru import NAMA_SITUS
from sela.setelan import Setelan
from sela.worker import ukuran_dir

DIR = Path(__file__).parent
CSP = "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
METODE_UBAH = ("POST", "PUT", "PATCH", "DELETE")


@dataclass
class Layanan:
    buka_db: Callable[[], sqlite3.Connection]
    pengambil: object
    drive: object
    cache: object
    worker: object = None


def buat_app(s: Setelan, l: Layanan) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.s = s
    app.state.l = l
    app.state.templates = Jinja2Templates(directory=DIR / "templates")
    app.mount("/static", StaticFiles(directory=DIR / "static"), name="static")

    @app.exception_handler(HTTPException)
    async def galat_http(request: Request, exc: HTTPException):
        if exc.status_code == 401:
            return JSONResponse({"galat": "sesi_habis"}, status_code=401)
        if exc.status_code == 303:
            return respons_tanpa_sesi(request.url.path)
        return JSONResponse({"galat": exc.detail}, status_code=exc.status_code, headers=exc.headers)

    pasang_rute_auth(app, s)
    pasang_api(app)

    def render(request: Request, nama: str, konteks: dict, conn: sqlite3.Connection, panel: bool = False):
        if panel:
            konteks |= {"kejadian": tampilan.aktivitas(conn, 6), "sumber_bermasalah": conn.execute(
                "select 1 from series_sources where jenis_error is not null").fetchone() is not None}
        return app.state.templates.TemplateResponse(request, nama, konteks | {"panel": panel})

    def koneksi():
        conn = l.buka_db()
        try:
            yield conn
        finally:
            conn.close()

    @app.get("/")
    def beranda(request: Request, u=Depends(pengguna_html), conn=Depends(koneksi)):
        isi = tampilan.rak(conn, u["id"])
        pertama = None
        for d in isi:
            c = tampilan.chapter_pertama_siap(conn, d["id"])
            if c:
                pertama = {"judul": d["judul"], "chapter_id": c["id"]}
                break
        return render(request, "beranda.html", {
            "u": u, "aktif": "beranda", "nama": u["nama"] or u["email"].split("@")[0], "rak": isi,
            "total_baru": sum(d["baru"] for d in isi), "lanjut": tampilan.lanjut_baca(conn, u["id"]),
            "ring": tampilan.ringkasan(conn), "pertama": pertama}, conn, panel=True)

    @app.get("/rak")
    def rak(request: Request, q: str | None = None, f: str | None = None, u=Depends(pengguna_html), conn=Depends(koneksi)):
        aktif = "riwayat" if f == "dibaca" else "rak"
        return render(request, "rak.html", {"u": u, "aktif": aktif, "rak": tampilan.rak(conn, u["id"], q, f), "q": q, "f": f},
                      conn, panel=True)

    @app.get("/judul/{series_id}")
    def judul(request: Request, series_id: int, f: str | None = None, urut: str = "baru", u=Depends(pengguna_html),
              conn=Depends(koneksi)):
        urut = "lama" if urut == "lama" else "baru"
        d = tampilan.detail(conn, u["id"], series_id, f, urut)
        if d is None:
            raise HTTPException(404, detail="judul tidak ditemukan")
        resp = render(request, "judul.html", {"u": u, "aktif": "rak", "d": d, "f": f, "urut": urut}, conn)
        progres.catat_kunjungan(conn, u["id"], series_id, time.time())
        return resp

    @app.get("/aktivitas")
    def halaman_aktivitas(request: Request, u=Depends(pengguna_html), conn=Depends(koneksi)):
        sumber = [dict(x) | {"situs": NAMA_SITUS[x["adapter"]], "dicek": tampilan.waktu_relatif(x["cek_sukses_terakhir"])}
                  for x in conn.execute("select ss.*, s.judul from series_sources ss join series s on s.id=ss.series_id "
                                        "order by ss.jenis_error is null, s.judul")]
        berjalan = []
        for j in conn.execute("select j.checkpoint, c.label, s.judul from jobs j join chapters c on c.id=j.target "
                              "join series s on s.id=c.series_id where j.status='berjalan'"):
            cp = json.loads(j["checkpoint"])
            berjalan.append({"judul": j["judul"], "label": j["label"], "gambar_selesai": cp.get("gambar_selesai", 0),
                             "gambar_total": cp.get("gambar_total", 0)})
        return render(request, "aktivitas.html", {
            "u": u, "aktif": "aktivitas", "kejadian": tampilan.aktivitas(conn), "sumber": sumber, "berjalan": berjalan,
            "ring": tampilan.ringkasan(conn), "drive_status": db.kv_ambil(conn, "drive_status"),
            "antrean_jeda": db.kv_ambil(conn, "antrean_jeda") == "1",
            "disk": {"terpakai": ukuran_dir(s.dir_tmp) + ukuran_dir(s.dir_cache), "anggaran": s.anggaran_disk}}, conn)

    @app.get("/akun")
    def akun(request: Request, u=Depends(pengguna_html), conn=Depends(koneksi)):
        return render(request, "akun.html", {"u": u, "aktif": "akun", "drive_status": db.kv_ambil(conn, "drive_status")}, conn)

    # urutan middleware: yang ditambahkan terakhir paling luar
    @app.middleware("http")
    async def jaga_sesi(request: Request, call_next):
        if butuh_sesi(request.url.path) and not request.session.get("uid"):
            return respons_tanpa_sesi(request.url.path)
        return await call_next(request)

    @app.middleware("http")
    async def jaga_origin(request: Request, call_next):
        if request.method in METODE_UBAH and request.headers.get("origin") != s.base_url:
            return JSONResponse({"galat": "origin_ditolak"}, status_code=403)
        return await call_next(request)

    app.add_middleware(SessionMiddleware, secret_key=s.session_secret, session_cookie="sela", max_age=30 * 86400,
                       same_site="lax", https_only=True)

    @app.middleware("http")
    async def header_keamanan(request: Request, call_next):
        r = await call_next(request)
        r.headers["content-security-policy"] = CSP
        r.headers["x-content-type-options"] = "nosniff"
        r.headers["referrer-policy"] = "same-origin"
        return r

    return app
