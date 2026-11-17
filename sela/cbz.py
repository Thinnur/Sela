import hashlib
import io
import json
import threading
import zipfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError

MAKS_PIKSEL = 25_000_000  # RGB 25 juta piksel sekitar 75 MB; dua decode bersamaan tetap jauh di bawah MemoryMax 512M
FORMAT = {"JPEG": ("image/jpeg", "jpg"), "PNG": ("image/png", "png"), "WEBP": ("image/webp", "webp"),
          "GIF": ("image/gif", "gif")}
# satu strip manhwa panjang bisa memakan puluhan MB RAM saat di-decode
_DECODE = threading.BoundedSemaphore(2)


class GambarRusak(Exception):
    pass


@dataclass(frozen=True)
class InfoGambar:
    mime: str
    ext: str
    lebar: int
    tinggi: int


@dataclass(frozen=True)
class HasilCbz:
    path: Path
    ukuran: int
    md5: str
    sha256: str
    jumlah: int
    manifest: dict


def periksa_gambar(data: bytes) -> InfoGambar:
    if not data:
        raise GambarRusak("berkas gambar kosong")
    with _DECODE:
        try:
            with Image.open(io.BytesIO(data)) as img:
                if img.format not in FORMAT:
                    raise GambarRusak(f"format tidak didukung: {img.format}")
                lebar, tinggi = img.size
                if lebar * tinggi > MAKS_PIKSEL:
                    raise GambarRusak("gambar terlalu besar untuk di-decode")
                img.load()
                mime, ext = FORMAT[img.format]
        except GambarRusak:
            raise
        except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError) as e:
            raise GambarRusak("gambar rusak atau bukan gambar") from e
    return InfoGambar(mime, ext, lebar, tinggi)


def buat_cbz(tujuan: Path, berkas: list[tuple[Path, InfoGambar, str]], info_sumber: dict) -> HasilCbz:
    gambar = []
    with zipfile.ZipFile(tujuan, "w", compression=zipfile.ZIP_STORED) as z:
        for n, (path, info, host) in enumerate(berkas, 1):
            data = Path(path).read_bytes()
            nama = f"{n:04d}.{info.ext}"
            z.writestr(nama, data)
            gambar.append({"n": n, "nama": nama, "mime": info.mime, "lebar": info.lebar, "tinggi": info.tinggi,
                           "ukuran": len(data), "sha256": hashlib.sha256(data).hexdigest(), "host": host})
        manifest = {"versi": 1, "sumber": info_sumber, "gambar": gambar}
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
    return hasil_dari(Path(tujuan))


def hasil_dari(path: Path) -> HasilCbz:
    md5, sha = hashlib.md5(), hashlib.sha256()
    with open(path, "rb") as f:
        for potong in iter(lambda: f.read(1 << 20), b""):
            md5.update(potong)
            sha.update(potong)
    manifest = baca_manifest(path)
    return HasilCbz(Path(path), Path(path).stat().st_size, md5.hexdigest(), sha.hexdigest(), len(manifest["gambar"]), manifest)


def baca_manifest(path: Path) -> dict:
    with zipfile.ZipFile(path) as z:
        return json.loads(z.read("manifest.json"))


def baca_entri(path: Path, n: int) -> tuple[bytes, str]:
    with zipfile.ZipFile(path) as z:
        gambar = json.loads(z.read("manifest.json"))["gambar"]
        if not 1 <= n <= len(gambar):
            raise LookupError(f"gambar ke-{n} tidak ada")
        entri = gambar[n - 1]
        return z.read(entri["nama"]), entri["mime"]
