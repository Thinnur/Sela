from fastapi.testclient import TestClient

from sela import db
from sela.main import buat
from tests.conftest import ENV


def test_titik_masuk_hidup_dan_drive_belum_tersambung(tmp_path):
    env = {**ENV, "SELA_ROOT": str(tmp_path / "root"), "SELA_BASE_URL": "https://sela.akzara.id"}
    app = buat(env)
    with TestClient(app, base_url="https://sela.akzara.id") as c:
        assert c.get("/masuk").status_code == 200
        assert c.get("/").status_code == 200 and c.get("/", follow_redirects=False).status_code == 303
    conn = db.buka(tmp_path / "root" / "data" / "sela.db")
    assert db.kv_ambil(conn, "drive_status") == "perlu_sambung"
    assert conn.execute("select count(*) from users").fetchone()[0] == 2
