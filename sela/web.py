import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from sela.auth import butuh_sesi, pasang_rute_auth, pengguna_html, respons_tanpa_sesi
from sela.setelan import Setelan

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

    @app.get("/")
    def beranda(request: Request, u=Depends(pengguna_html)):
        return app.state.templates.TemplateResponse(request, "beranda.html", {"u": u})

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
