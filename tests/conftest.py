import pytest

from sela import db
from sela.setelan import muat_setelan

ENV = {
    "SELA_ROOT": "/tmp/sela-uji",
    "SELA_ALLOWED_EMAILS": "a@x.com, b@x.com",
    "SELA_ADMIN_EMAIL": "a@x.com",
    "SELA_BASE_URL": "https://sela.akzara.id",
    "SELA_SESSION_SECRET": "s" * 32,
}


@pytest.fixture
def setelan(tmp_path):
    return muat_setelan({**ENV, "SELA_ROOT": str(tmp_path / "root")})


@pytest.fixture
def conn(tmp_path):
    c = db.buka(tmp_path / "uji.db")
    db.migrasi(c)
    yield c
    c.close()
