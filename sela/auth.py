import sqlite3

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from sela.setelan import Setelan

PUBLIK = ("/masuk", "/masuk/google", "/auth/callback")
PUBLIK_AWALAN = ("/static/", "/dev/masuk/")
LOOPBACK = ("127.0.0.1", "::1")
GOOGLE_META = "https://accounts.google.com/.well-known/openid-configuration"


def izinkan_login(conn: sqlite3.Connection, s: Setelan, info: dict) -> int | None:
    """Pilih akun Sela untuk identitas Google yang sudah diverifikasi. None berarti ditolak."""
    sub, email = info.get("sub"), (info.get("email") or "").strip().lower()
    if info.get("email_verified") is not True or not sub:
        return None
    nama = (info.get("name") or "").strip()
    r = conn.execute("select id from users where google_sub=?", (sub,)).fetchone()
    if r is None:
        if email not in s.allowed_emails:
            return None
        r = conn.execute("select id, google_sub from users where email=?", (email,)).fetchone()
        if r is None or r["google_sub"] is not None:
            return None  # email ini sudah terikat ke akun Google lain
        conn.execute("update users set google_sub=? where id=?", (sub, r["id"]))
    if nama:
        conn.execute("update users set nama=? where id=?", (nama, r["id"]))
    return r["id"]


def _pengguna(request: Request) -> sqlite3.Row | None:
    uid = request.session.get("uid")
    if not uid:
        return None
    conn = request.app.state.l.buka_db()
    try:
        return conn.execute("select * from users where id=?", (uid,)).fetchone()
    finally:
        conn.close()


def pengguna_html(request: Request) -> sqlite3.Row:
    u = _pengguna(request)
    if u is None:
        raise HTTPException(303, headers={"location": "/masuk"})
    return u


def pengguna_api(request: Request) -> sqlite3.Row:
    u = _pengguna(request)
    if u is None:
        raise HTTPException(401, detail="sesi_habis")
    return u


def wajib_admin(u: sqlite3.Row) -> None:
    if u["peran"] != "admin":
        raise HTTPException(403, detail="khusus_admin")


def respons_tanpa_sesi(path: str) -> Response:
    if path.startswith(("/api/", "/sampul/")):
        return JSONResponse({"galat": "sesi_habis"}, status_code=401)
    return RedirectResponse("/masuk", status_code=303)


def butuh_sesi(path: str) -> bool:
    return path not in PUBLIK and not path.startswith(PUBLIK_AWALAN)


def pasang_rute_auth(app: FastAPI, s: Setelan) -> None:
    oauth = OAuth()
    if s.google_client_id:
        oauth.register("google", client_id=s.google_client_id, client_secret=s.google_client_secret,
                       server_metadata_url=GOOGLE_META, client_kwargs={"scope": "openid email profile"})

    @app.get("/masuk")
    def masuk(request: Request):
        return app.state.templates.TemplateResponse(request, "masuk.html", {})

    @app.get("/masuk/google")
    async def masuk_google(request: Request):
        if not s.google_client_id:
            raise HTTPException(503, detail="login Google belum dikonfigurasi")
        return await oauth.google.authorize_redirect(request, f"{s.base_url}/auth/callback")

    @app.get("/auth/callback")
    async def callback(request: Request):
        try:
            token = await oauth.google.authorize_access_token(request)
        except (OAuthError, AttributeError):
            return RedirectResponse("/masuk", status_code=303)
        conn = app.state.l.buka_db()
        try:
            uid = izinkan_login(conn, s, token.get("userinfo") or {})
        finally:
            conn.close()
        if uid is None:
            return app.state.templates.TemplateResponse(request, "ditolak.html", {}, status_code=403)
        request.session.clear()
        request.session["uid"] = uid
        return RedirectResponse("/", status_code=303)

    @app.post("/keluar")
    def keluar(request: Request):
        request.session.clear()
        return RedirectResponse("/masuk", status_code=303)

    @app.get("/dev/masuk/{user_id}")
    def dev_masuk(request: Request, user_id: int):
        if not s.dev_login or (request.client and request.client.host) not in LOOPBACK:
            raise HTTPException(404)
        request.session.clear()
        request.session["uid"] = user_id
        return RedirectResponse("/", status_code=303)
