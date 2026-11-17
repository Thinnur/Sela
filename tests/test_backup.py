import asyncio
import json
import os
import sqlite3
import stat
from dataclasses import replace

from fastapi.testclient import TestClient

from sela import db
from sela.backup import backup_db, detik_menuju
from sela.drive import DriveLokal, TokenDrive
from sela.web import Layanan, buat_app

WIB = 7 * 3600


def test_backup_menyisakan_14(tmp_path):
    path_db = tmp_path / "sela.db"
    c = sqlite3.connect(path_db)
    c.execute("create table x(a)")
    c.execute("insert into x values(42)")
    c.commit()
    c.close()
    d = DriveLokal(tmp_path / "drive")
    src = tmp_path / "lama"
    src.write_bytes(b"lama")
    for i in range(15):
        asyncio.run(d.unggah(src, f"sela-202601{i + 10:02d}-0300.db", "x", {"sela_backup": "1"}))
    lain = asyncio.run(d.unggah(src, "ch-1.cbz", "x", {"sela_chapter": "1"}))
    asyncio.run(backup_db(path_db, d, tmp_path / "tmp", 1_794_970_800.0))
    cadangan = sorted(b["nama"] for b in d.semua() if b["app_props"].get("sela_backup"))
    assert len(cadangan) == 14 and cadangan[-1].startswith("sela-20261118") and "sela-20260110-0300.db" not in cadangan
    assert d.berkas(lain.id).nama == "ch-1.cbz"
    terbaru = next(b for b in d.semua() if b["nama"] == cadangan[-1])
    salin = tmp_path / "salin.db"
    asyncio.run(d.unduh(terbaru["id"], salin))
    assert sqlite3.connect(salin).execute("select a from x").fetchone() == (42,)
    assert not list((tmp_path / "tmp").iterdir())


def test_detik_menuju_jam_3_wib():
    tengah_malam_wib = 1_794_934_800.0  # 18 Nov 2026 00:00 WIB
    assert detik_menuju(3, tengah_malam_wib + 2 * 3600) == 3600
    assert detik_menuju(3, tengah_malam_wib + 4 * 3600) == 23 * 3600


def test_token_disimpan_mode_600(tmp_path):
    t = TokenDrive(tmp_path / "s" / "drive.json", "c", "s")
    t.simpan({"access_token": "A", "refresh_token": "R", "expires_in": 3600})
    p = tmp_path / "s" / "drive.json"
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o600 and json.loads(p.read_text())["refresh_token"] == "R"


def test_drive_hanya_admin(tmp_path, setelan):
    s = replace(setelan, dev_login=True)
    p = tmp_path / "d.db"
    c = db.buka(p)
    db.migrasi(c)
    db.pastikan_pengguna(c, s)
    c.close()
    app = buat_app(s, Layanan(lambda: db.buka(p), None, None, None))
    for uid, harap in ((2, 403), (1, 503)):
        k = TestClient(app, base_url="https://sela.akzara.id", client=("127.0.0.1", 1))
        k.get(f"/dev/masuk/{uid}")
        assert k.get("/akun/drive", follow_redirects=False).status_code == harap
        assert k.get("/akun/drive/callback", follow_redirects=False).status_code == harap
