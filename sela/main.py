"""Titik masuk: uvicorn sela.main:app --host 127.0.0.1 --port 8095"""
import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager

import httpx

from sela import db, pembaru
from sela.cache import CacheChapter
from sela.drive import DriveHttp, DriveLokal, TokenDrive
from sela.fetch import PengambilAman
from sela.setelan import Setelan, muat_setelan
from sela.web import Layanan, buat_app
from sela.worker import Worker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def token_drive(s: Setelan) -> TokenDrive:
    return TokenDrive(s.dir_secrets / "drive.json", s.google_client_id, s.google_client_secret)


def buat(env=os.environ):
    s = muat_setelan(env)
    for d in (s.dir_data, s.dir_cache, s.dir_tmp, s.dir_secrets):
        d.mkdir(parents=True, exist_ok=True)
    path_db = s.dir_data / "sela.db"
    conn = db.buka(path_db)
    db.migrasi(conn)
    db.pastikan_pengguna(conn, s)

    def buka_db():
        return db.buka(path_db)

    pengambil = PengambilAman(httpx.AsyncClient(timeout=httpx.Timeout(30, connect=10)), per_situs=s.request_per_situs)
    if env.get("SELA_DRIVE_LOKAL") == "1":
        drive = DriveLokal(s.root / "drive-lokal")
    else:
        token = token_drive(s)
        drive = DriveHttp(httpx.AsyncClient(timeout=httpx.Timeout(120, connect=10)), token)
        if not token.ada():
            db.kv_set(conn, "drive_status", "perlu_sambung")
    conn.close()

    async def detak():
        c = buka_db()
        try:
            return await pembaru.detak(c, pengambil, s, time.time())
        finally:
            c.close()

    worker = Worker(s, buka_db, pengambil, drive, detak=detak)
    l = Layanan(buka_db, pengambil, drive, CacheChapter(s.dir_cache, s.cache_maks, drive), worker)
    app = buat_app(s, l)

    @asynccontextmanager
    async def lifespan(_app):
        worker.pulihkan()
        tugas = asyncio.create_task(worker.jalan())
        yield
        tugas.cancel()

    app.router.lifespan_context = lifespan
    return app


app = buat() if os.environ.get("SELA_ROOT") else None
