import asyncio
import hashlib
import json
import time

import httpx
import pytest

from sela.drive import BerkasDrive, DriveError, DriveHttp, DriveLokal, TokenDrive


def token(tmp_path, kedaluwarsa=None):
    p = tmp_path / "drive.json"
    p.write_text(json.dumps({"access_token": "lama", "refresh_token": "R", "kedaluwarsa": kedaluwarsa or time.time() + 3600}))
    return TokenDrive(p, "cid", "csecret")


def drive(tmp_path, handler, **kw):
    return DriveHttp(httpx.AsyncClient(transport=httpx.MockTransport(handler)), token(tmp_path, **kw))


def jenis_error(coro):
    with pytest.raises(DriveError) as e:
        asyncio.run(coro)
    return e.value.jenis


def test_unggah_resumable_kirim_metadata(tmp_path):
    berkas = tmp_path / "ch.cbz"
    berkas.write_bytes(b"isi-cbz")
    terlihat = {}

    def handler(request):
        if request.method == "POST":
            assert request.url.params["uploadType"] == "resumable"
            assert str(request.url).startswith("https://www.googleapis.com/upload/drive/v3/files")
            terlihat["meta"] = json.loads(request.content)
            return httpx.Response(200, headers={"location": "https://www.googleapis.com/upload/drive/v3/files?upload_id=X"})
        assert request.method == "PUT" and request.content == b"isi-cbz"
        assert request.headers["authorization"] == "Bearer lama"
        return httpx.Response(200, json={"id": "F1", "name": "ch-1.cbz", "size": "7",
                                         "md5Checksum": hashlib.md5(b"isi-cbz").hexdigest()})

    hasil = asyncio.run(drive(tmp_path, handler).unggah(berkas, "ch-1.cbz", "INDUK", {"sela_chapter": "12"}))
    assert hasil == BerkasDrive("F1", "ch-1.cbz", 7, hashlib.md5(b"isi-cbz").hexdigest())
    assert terlihat["meta"] == {"name": "ch-1.cbz", "parents": ["INDUK"], "appProperties": {"sela_chapter": "12"}}


def test_cari_memakai_appproperties(tmp_path):
    terlihat = {}

    def handler(request):
        terlihat["q"] = request.url.params["q"]
        terlihat["fields"] = request.url.params["fields"]
        return httpx.Response(200, json={"files": [{"id": "F1", "name": "a", "size": "3", "md5Checksum": "m"}]})

    hasil = asyncio.run(drive(tmp_path, handler).cari({"sela_chapter": "12"}))
    assert hasil == [BerkasDrive("F1", "a", 3, "m")]
    assert "appProperties has { key='sela_chapter' and value='12' }" in terlihat["q"] and "trashed = false" in terlihat["q"]
    assert "md5Checksum" in terlihat["fields"] and "size" in terlihat["fields"]


def test_refresh_saat_401_lalu_ulang(tmp_path):
    panggilan = []

    def handler(request):
        panggilan.append((request.method, request.url.host, request.headers.get("authorization")))
        if request.url.host == "oauth2.googleapis.com":
            assert b"grant_type=refresh_token" in request.content and b"refresh_token=R" in request.content
            return httpx.Response(200, json={"access_token": "baru", "expires_in": 3600})
        if request.headers["authorization"] == "Bearer lama":
            return httpx.Response(401, json={"error": {"code": 401}})
        return httpx.Response(200, json={"files": []})

    assert asyncio.run(drive(tmp_path, handler).cari({"a": "b"})) == []
    assert panggilan[-1][2] == "Bearer baru"
    assert json.loads((tmp_path / "drive.json").read_text())["refresh_token"] == "R"


def test_invalid_grant_jadi_auth(tmp_path):
    def handler(request):
        return httpx.Response(400, json={"error": "invalid_grant"})

    assert jenis_error(drive(tmp_path, handler, kedaluwarsa=1).cari({"a": "b"})) == "auth"


def test_403_rate_limit_jadi_dibatasi(tmp_path):
    def handler(request):
        return httpx.Response(403, json={"error": {"code": 403, "errors": [{"reason": "userRateLimitExceeded"}]}})

    assert jenis_error(drive(tmp_path, handler).cari({"a": "b"})) == "dibatasi"


def test_error_tidak_membocorkan_token(tmp_path):
    def handler(request):
        return httpx.Response(500, text="x")

    with pytest.raises(DriveError) as e:
        asyncio.run(drive(tmp_path, handler).cari({"a": "b"}))
    assert e.value.jenis == "sementara" and "lama" not in str(e.value) and "R" not in e.value.pesan.split()


def test_drive_lokal_bolak_balik(tmp_path):
    d = DriveLokal(tmp_path / "drive")
    src = tmp_path / "x.cbz"
    src.write_bytes(b"halo")

    async def jalan():
        induk = await d.pastikan_folder("Sela", None)
        assert await d.pastikan_folder("Sela", None) == induk
        b = await d.unggah(src, "x.cbz", induk, {"sela_chapter": "1"})
        assert await d.cari({"sela_chapter": "1"}) == [b]
        await d.unduh(b.id, tmp_path / "balik")
        return b

    b = asyncio.run(jalan())
    assert (tmp_path / "balik").read_bytes() == b"halo" and b.md5 == hashlib.md5(b"halo").hexdigest()
    assert d.jumlah() == 1 and d.berkas(b.id) == b
