import io
import struct
import zlib

from PIL import Image


def gambar_bytes(fmt: str, w: int = 20, h: int = 30, warna=(200, 120, 80)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), warna).save(buf, fmt)
    return buf.getvalue()


def webp_bytes(w: int = 20, h: int = 30) -> bytes:
    return gambar_bytes("WEBP", w, h)


def jpeg_bytes(w: int = 20, h: int = 30) -> bytes:
    return gambar_bytes("JPEG", w, h)


def png_bytes(w: int = 20, h: int = 30) -> bytes:
    return gambar_bytes("PNG", w, h)


def png_raksasa(w: int = 20000, h: int = 20000) -> bytes:
    """PNG kecil yang header IHDR-nya mengaku berukuran raksasa (bom dekompresi)."""
    data = bytearray(png_bytes(1, 1))
    ihdr = bytearray(data[12:29])
    ihdr[4:8] = struct.pack(">I", w)
    ihdr[8:12] = struct.pack(">I", h)
    data[12:29] = ihdr
    data[29:33] = struct.pack(">I", zlib.crc32(bytes(ihdr)))
    return bytes(data)
