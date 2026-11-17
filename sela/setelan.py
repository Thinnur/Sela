from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

WAJIB = ("SELA_ROOT", "SELA_ALLOWED_EMAILS", "SELA_ADMIN_EMAIL", "SELA_BASE_URL", "SELA_SESSION_SECRET")


@dataclass(frozen=True)
class Setelan:
    root: Path
    allowed_emails: frozenset[str]
    admin_email: str
    base_url: str
    session_secret: str
    chapter_paralel: int = 3
    request_per_situs: int = 8
    anggaran_disk: int = 1_500_000_000
    cache_maks: int = 1_000_000_000
    sisa_disk_min: int = 3_000_000_000
    interval_cek: int = 21600
    jitter_cek: int = 1800
    cooldown_cek_manual: int = 600
    dev_login: bool = False

    @property
    def dir_data(self) -> Path:
        return self.root / "data"

    @property
    def dir_cache(self) -> Path:
        return self.root / "cache"

    @property
    def dir_tmp(self) -> Path:
        return self.root / "tmp"

    @property
    def dir_secrets(self) -> Path:
        return self.root / "secrets"


def muat_setelan(env: Mapping[str, str]) -> Setelan:
    hilang = [k for k in WAJIB if not env.get(k, "").strip()]
    if hilang:
        raise ValueError(f"env wajib belum diisi: {', '.join(hilang)}")
    emails = frozenset(e.strip().lower() for e in env["SELA_ALLOWED_EMAILS"].split(",") if e.strip())
    admin = env["SELA_ADMIN_EMAIL"].strip().lower()
    if admin not in emails:
        raise ValueError("SELA_ADMIN_EMAIL harus ada di SELA_ALLOWED_EMAILS")
    return Setelan(
        root=Path(env["SELA_ROOT"]),
        allowed_emails=emails,
        admin_email=admin,
        base_url=env["SELA_BASE_URL"].rstrip("/"),
        session_secret=env["SELA_SESSION_SECRET"],
        chapter_paralel=min(4, max(1, int(env.get("SELA_CHAPTER_PARALEL", "3")))),
        dev_login=env.get("SELA_DEV_LOGIN") == "1",
    )
