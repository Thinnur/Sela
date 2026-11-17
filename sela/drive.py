import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

import httpx

API = "https://www.googleapis.com/drive/v3/files"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
TOKEN_URL = "https://oauth2.googleapis.com/token"
FOLDER = "application/vnd.google-apps.folder"
FIELDS = "id,name,size,md5Checksum"

JenisDrive = Literal["auth", "dibatasi", "sementara", "lain"]


class DriveError(Exception):
    def __init__(self, jenis: JenisDrive, pesan: str):
        super().__init__(f"{jenis}: {pesan}")
        self.jenis = jenis
        self.pesan = pesan


@dataclass(frozen=True)
class BerkasDrive:
    id: str
    nama: str
    ukuran: int
    md5: str


class Drive(Protocol):
    async def pastikan_folder(self, nama: str, induk: str | None) -> str: ...
    async def cari(self, app_props: dict[str, str]) -> list[BerkasDrive]: ...
    async def unggah(self, path: Path, nama: str, induk: str, app_props: dict[str, str]) -> BerkasDrive: ...
    async def unduh(self, file_id: str, tujuan: Path) -> None: ...
    async def hapus(self, file_id: str) -> None: ...


def tulis_rahasia(path: Path, isi: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(isi)
    os.chmod(path, 0o600)


class TokenDrive:
    def __init__(self, path: Path, client_id: str, client_secret: str):
        self.path = Path(path)
        self.client_id = client_id
        self.client_secret = client_secret

    def ada(self) -> bool:
        return self.path.exists()

    def _muat(self) -> dict:
        try:
            return json.loads(self.path.read_text())
        except (OSError, ValueError) as e:
            raise DriveError("auth", "Drive belum disambungkan") from e

    def simpan(self, token: dict) -> None:
        lama = json.loads(self.path.read_text()) if self.path.exists() else {}
        data = {
            "access_token": token["access_token"],
            "refresh_token": token.get("refresh_token") or lama.get("refresh_token"),
            "kedaluwarsa": token.get("expires_at") or time.time() + float(token.get("expires_in", 3600)),
        }
        if not data["refresh_token"]:
            raise DriveError("auth", "Google tidak memberi refresh token")
        tulis_rahasia(self.path, json.dumps(data))

    async def akses(self, client: httpx.AsyncClient, paksa: bool = False) -> str:
        t = self._muat()
        if not paksa and t.get("kedaluwarsa", 0) > time.time() + 60:
            return t["access_token"]
        try:
            r = await client.post(TOKEN_URL, data={"grant_type": "refresh_token", "refresh_token": t["refresh_token"],
                                                    "client_id": self.client_id, "client_secret": self.client_secret})
        except httpx.TransportError as e:
            raise DriveError("sementara", "gagal menghubungi Google") from e
        if r.status_code in (400, 401):
            raise DriveError("auth", "izin Drive dicabut atau kedaluwarsa, sambungkan ulang")
        if r.status_code != 200:
            raise DriveError("sementara", f"refresh token gagal (HTTP {r.status_code})")
        self.simpan(r.json())
        return self._muat()["access_token"]


def _berkas(d: dict) -> BerkasDrive:
    return BerkasDrive(d["id"], d.get("name", ""), int(d.get("size", 0)), d.get("md5Checksum", ""))


def _kutip(nilai: str) -> str:
    return nilai.replace("\\", "\\\\").replace("'", "\\'")


def _alasan(r: httpx.Response) -> set[str]:
    try:
        return {e.get("reason", "") for e in r.json().get("error", {}).get("errors", [])}
    except (ValueError, AttributeError):
        return set()


class DriveHttp:
    def __init__(self, client: httpx.AsyncClient, token: TokenDrive):
        self.client = client
        self.token = token

    async def _req(self, method: str, url: str, **kw) -> httpx.Response:
        for percobaan in range(2):
            tok = await self.token.akses(self.client, paksa=percobaan == 1)
            headers = {**kw.get("headers", {}), "authorization": f"Bearer {tok}"}
            try:
                r = await self.client.request(method, url, **{**kw, "headers": headers})
            except httpx.TransportError as e:
                raise DriveError("sementara", "koneksi ke Drive gagal") from e
            if r.status_code == 401 and percobaan == 0:
                continue
            self._cek(r)
            return r
        raise DriveError("auth", "Drive menolak token")

    def _cek(self, r: httpx.Response) -> None:
        s = r.status_code
        if s < 400:
            return
        alasan = _alasan(r)
        if s == 429 or alasan & {"userRateLimitExceeded", "rateLimitExceeded"}:
            raise DriveError("dibatasi", "Drive membatasi request")
        if s == 401 or alasan & {"insufficientPermissions", "authError"}:
            raise DriveError("auth", "izin Drive tidak cukup")
        if s >= 500:
            raise DriveError("sementara", f"Drive sedang bermasalah (HTTP {s})")
        raise DriveError("lain", f"Drive menolak request (HTTP {s})")

    async def pastikan_folder(self, nama: str, induk: str | None) -> str:
        q = f"mimeType='{FOLDER}' and name='{_kutip(nama)}' and trashed = false and '{_kutip(induk or 'root')}' in parents"
        r = await self._req("GET", API, params={"q": q, "fields": "files(id)", "spaces": "drive"})
        ada = r.json().get("files", [])
        if ada:
            return ada[0]["id"]
        r = await self._req("POST", API, params={"fields": "id"},
                            json={"name": nama, "mimeType": FOLDER, "parents": [induk or "root"]})
        return r.json()["id"]

    async def cari(self, app_props: dict[str, str]) -> list[BerkasDrive]:
        syarat = [f"appProperties has {{ key='{_kutip(k)}' and value='{_kutip(v)}' }}" for k, v in app_props.items()]
        q = " and ".join(syarat + ["trashed = false"])
        r = await self._req("GET", API, params={"q": q, "fields": f"files({FIELDS})", "spaces": "drive"})
        return [_berkas(f) for f in r.json().get("files", [])]

    async def unggah(self, path: Path, nama: str, induk: str, app_props: dict[str, str]) -> BerkasDrive:
        ukuran = Path(path).stat().st_size
        r = await self._req("POST", UPLOAD, params={"uploadType": "resumable", "fields": FIELDS},
                            headers={"x-upload-content-type": "application/octet-stream",
                                     "x-upload-content-length": str(ukuran)},
                            json={"name": nama, "parents": [induk], "appProperties": app_props})
        sesi = r.headers.get("location")
        if not sesi:
            raise DriveError("sementara", "Drive tidak memberi sesi unggah")
        # shortcut: unggahan terputus diulang dari awal (bukan dilanjutkan), cukup untuk CBZ belasan MB
        r = await self._req("PUT", sesi, content=Path(path).read_bytes(),
                            headers={"content-type": "application/octet-stream"})
        return _berkas(r.json())

    async def unduh(self, file_id: str, tujuan: Path) -> None:
        # shortcut: isi dibaca ke memori dulu, cukup untuk CBZ belasan MB; stream kalau arsip jadi ratusan MB
        r = await self._req("GET", f"{API}/{file_id}", params={"alt": "media"})
        Path(tujuan).write_bytes(r.content)

    async def hapus(self, file_id: str) -> None:
        await self._req("DELETE", f"{API}/{file_id}")


class DriveLokal:
    """Drive di folder lokal, untuk tes dan pengembangan."""

    def __init__(self, dir: Path, gagal_unggah: DriveError | None = None):
        self.dir = Path(dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.gagal_unggah = gagal_unggah
        self.gagal_unduh: DriveError | None = None
        self.jumlah_unduh = 0

    def _indeks(self) -> dict:
        p = self.dir / "indeks.json"
        return json.loads(p.read_text()) if p.exists() else {}

    def _simpan(self, indeks: dict) -> None:
        (self.dir / "indeks.json").write_text(json.dumps(indeks))

    def berkas(self, file_id: str) -> BerkasDrive:
        d = self._indeks()[file_id]
        return BerkasDrive(file_id, d["nama"], d["ukuran"], d["md5"])

    def jumlah(self) -> int:
        return sum(1 for d in self._indeks().values() if not d["folder"])

    def semua(self) -> list[dict]:
        return [{"id": k, **v} for k, v in self._indeks().items()]

    async def pastikan_folder(self, nama: str, induk: str | None) -> str:
        indeks = self._indeks()
        for k, d in indeks.items():
            if d["folder"] and d["nama"] == nama and d["induk"] == induk:
                return k
        k = uuid.uuid4().hex
        indeks[k] = {"nama": nama, "induk": induk, "folder": True, "app_props": {}, "ukuran": 0, "md5": ""}
        self._simpan(indeks)
        return k

    async def cari(self, app_props: dict[str, str]) -> list[BerkasDrive]:
        return [self.berkas(k) for k, d in self._indeks().items()
                if not d["folder"] and all(d["app_props"].get(a) == b for a, b in app_props.items())]

    async def unggah(self, path: Path, nama: str, induk: str, app_props: dict[str, str]) -> BerkasDrive:
        if self.gagal_unggah:
            raise self.gagal_unggah
        data = Path(path).read_bytes()
        k = uuid.uuid4().hex
        (self.dir / k).write_bytes(data)
        indeks = self._indeks()
        indeks[k] = {"nama": nama, "induk": induk, "folder": False, "app_props": dict(app_props),
                     "ukuran": len(data), "md5": hashlib.md5(data).hexdigest()}
        self._simpan(indeks)
        return self.berkas(k)

    async def unduh(self, file_id: str, tujuan: Path) -> None:
        if self.gagal_unduh:
            raise self.gagal_unduh
        self.jumlah_unduh += 1
        Path(tujuan).write_bytes((self.dir / file_id).read_bytes())

    async def hapus(self, file_id: str) -> None:
        indeks = self._indeks()
        indeks.pop(file_id, None)
        self._simpan(indeks)
        (self.dir / file_id).unlink(missing_ok=True)
