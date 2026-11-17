import hashlib
import json
import zipfile

import pytest

from sela.cbz import GambarRusak, InfoGambar, baca_entri, buat_cbz, periksa_gambar
from tests.gambar import jpeg_bytes, png_bytes, png_raksasa, webp_bytes


def test_tipe_dari_isi_bukan_nama():
    assert periksa_gambar(webp_bytes(20, 30)) == InfoGambar("image/webp", "webp", 20, 30)


@pytest.mark.parametrize("data", [jpeg_bytes()[:200], b"<html><title>Just a moment...</title></html>", b""])
def test_gambar_rusak_atau_html_ditolak(data):
    with pytest.raises(GambarRusak):
        periksa_gambar(data)


def test_bom_dekompresi_ditolak():
    with pytest.raises(GambarRusak):
        periksa_gambar(png_raksasa())


def tiga_gambar(tmp_path):
    hasil = []
    for i, data in enumerate([webp_bytes(), jpeg_bytes(), png_bytes()], 1):
        p = tmp_path / f"raw{i}"
        p.write_bytes(data)
        hasil.append((p, periksa_gambar(data), "img.komiku.org"))
    return hasil


def test_buat_cbz_urut_stored_dan_checksum(tmp_path):
    h = buat_cbz(tmp_path / "c.cbz", tiga_gambar(tmp_path), {"adapter": "komiku"})
    z = zipfile.ZipFile(h.path)
    assert z.namelist() == ["0001.webp", "0002.jpg", "0003.png", "manifest.json"]
    assert {i.compress_type for i in z.infolist()} == {zipfile.ZIP_STORED}
    assert h.md5 == hashlib.md5(h.path.read_bytes()).hexdigest() and h.jumlah == 3
    assert h.ukuran == h.path.stat().st_size
    assert baca_entri(h.path, 2) == (z.read("0002.jpg"), "image/jpeg")


def test_manifest_lengkap(tmp_path):
    h = buat_cbz(tmp_path / "c.cbz", tiga_gambar(tmp_path), {"adapter": "komiku"})
    m = json.loads(zipfile.ZipFile(h.path).read("manifest.json"))
    assert m == h.manifest and m["versi"] == 1 and m["sumber"] == {"adapter": "komiku"}
    g = m["gambar"][0]
    assert set(g) == {"n", "nama", "mime", "lebar", "tinggi", "ukuran", "sha256", "host"}
    assert (g["n"], g["nama"], g["mime"], g["lebar"], g["tinggi"], g["host"]) == (1, "0001.webp", "image/webp", 20, 30, "img.komiku.org")
    assert g["sha256"] == hashlib.sha256(webp_bytes()).hexdigest()


def test_baca_entri_di_luar_jangkauan(tmp_path):
    h = buat_cbz(tmp_path / "c.cbz", tiga_gambar(tmp_path), {})
    for n in (0, 4):
        with pytest.raises(LookupError):
            baca_entri(h.path, n)
