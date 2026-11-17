"""Isi data contoh untuk pengembangan dan uji tampilan: python -m sela.contoh

Memakai env yang sama dengan sela.main (SELA_ROOT dan kawan-kawan) dan DriveLokal di <root>/drive-lokal.
"""
import asyncio
import json
import os
import time

from PIL import Image, ImageDraw

from sela import db
from sela.cbz import buat_cbz, periksa_gambar
from sela.drive import DriveLokal
from sela.setelan import muat_setelan

WARNA = ["#3E5C8A", "#EF6B5B", "#4AA3A2", "#8B7FD0", "#F2B544", "#2E3F5E"]
PANEL = ["#BFD8E8", "#F6DCC8", "#EEE8F8", "#DDEFEE", "#FCEFD2"]
JUDUL = [("Money Keeps Piling Up No Matter How Much I Spend", "manhua", 8),
         ("Pedang Senja", "manhwa", 6), ("Kafe Ujung Gang", "manhwa", 4),
         ("Menara Lantai 99", "manhwa", 5), ("Musim Semi Kedua", "manga", 3), ("Bulan di Atap", "manga", 3)]


def sampul(path, warna, judul):
    img = Image.new("RGB", (300, 430), warna)
    d = ImageDraw.Draw(img)
    d.ellipse((90, 90, 210, 210), fill="#FBF6EE")
    d.rectangle((0, 330, 300, 430), fill="#3B2F2A")
    d.text((16, 350), judul[:28], fill="#FBF6EE")
    img.save(path, "WEBP")


def strip(path, n, label):
    img = Image.new("RGB", (720, 1100), "#FFFFFF")
    d = ImageDraw.Draw(img)
    for i, (y0, y1) in enumerate([(20, 520), (540, 1080)]):
        d.rectangle((20, y0, 700, y1), fill=PANEL[(n + i) % len(PANEL)], outline="#3B2F2A", width=4)
        d.ellipse((60, y0 + 30, 360, y0 + 150), fill="#FFFFFF", outline="#3B2F2A", width=3)
        d.text((100, y0 + 80), f"{label}, panel {n * 2 + i + 1}", fill="#3B2F2A")
    img.save(path, "WEBP")


async def isi():
    s = muat_setelan(os.environ)
    for p in (s.dir_data / "sampul", s.dir_cache, s.dir_tmp):
        p.mkdir(parents=True, exist_ok=True)
    conn = db.buka(s.dir_data / "sela.db")
    db.migrasi(conn)
    db.pastikan_pengguna(conn, s)
    if conn.execute("select count(*) from series").fetchone()[0]:
        print("data contoh sudah ada")
        return
    drive = DriveLokal(s.root / "drive-lokal")
    nama = ["Fathin", "Putri"]
    for i, email in enumerate(sorted(s.allowed_emails, key=lambda e: e != s.admin_email)):
        conn.execute("update users set nama=? where email=?", (nama[i] if i < 2 else email, email))
    sekarang = time.time()
    for sid, (judul, jenis, jumlah) in enumerate(JUDUL, 1):
        sampul(s.dir_data / "sampul" / f"{sid}.webp", WARNA[sid - 1], judul)
        conn.execute("insert into series(id, judul, jenis, sinopsis, sampul, ditambahkan_oleh, ditambahkan_pada) "
                     "values(?,?,?,?,?,1,?)", (sid, judul, jenis, "Judul contoh untuk mencoba tampilan Sela.", f"{sid}.webp",
                                               sekarang - 1000 * sid))
        conn.execute("insert into series_sources(id, series_id, adapter, url, peran, cek_sukses_terakhir, cek_berikutnya) "
                     "values(?,?, 'komiku', ?, 'utama', ?, ?)", (sid, sid, f"https://komiku.org/manga/contoh-{sid}/",
                                                                 sekarang - 7200, sekarang + 10 ** 7))
        for n in range(1, jumlah + 1):
            status = "siap"
            if sid == 1 and n == jumlah:
                status = "mengunduh"
            elif sid == 1 and n == jumlah - 1:
                status = "gagal"
            cid = conn.execute("insert into chapters(series_id, label, label_normal, kunci_urut, status, pesan_status, siap_pada, terbit) "
                               "values(?,?,?,?,?,?,?,?)", (sid, f"Chapter {n}", str(n), n, status,
                                                           "gambar ke-2 rusak" if status == "gagal" else None,
                                                           sekarang - 3600 * (jumlah - n), f"{n:02d}/11/2026")).lastrowid
            conn.execute("insert into chapter_sources values(?,?,?)", (cid, sid, f"https://komiku.org/contoh-{sid}-chapter-{n}/"))
            if status != "siap":
                continue
            kerja = s.dir_tmp / f"contoh-{cid}"
            kerja.mkdir(parents=True, exist_ok=True)
            berkas = []
            for g in range(4):
                p = kerja / f"{g:04d}"
                strip(p, g, f"Chapter {n}")
                berkas.append((p, periksa_gambar(p.read_bytes()), "contoh"))
            h = buat_cbz(kerja / "ch.cbz", berkas, {"adapter": "contoh"})
            b = await drive.unggah(h.path, f"ch-{n}.cbz", "contoh", {"sela_chapter": str(cid)})
            conn.execute("insert into archives values(?,?,?,?,?,?,?,?,?)", (cid, b.id, sid, h.ukuran, h.md5, h.sha256, h.jumlah,
                                                                           json.dumps(h.manifest), sekarang))
            for f in kerja.iterdir():
                f.unlink()
            kerja.rmdir()
    conn.execute("insert into reading_progress values(1, 1, 3, 1, 0.4, 1, ?)", (sekarang,))
    conn.execute("insert into chapter_reads values(1, 1, 'selesai', ?), (1, 2, 'selesai', ?), (1, 3, 'dibaca', ?)",
                 (sekarang, sekarang, sekarang))
    conn.execute("insert into reading_progress values(1, 3, 15, 0, 0.2, 1, ?)", (sekarang - 5000,))
    for teks, uid in [("Putri menambahkan Kafe Ujung Gang", 2), ("Chapter 8 terbit di Komiku", None),
                      ("Chapter 6 siap dibaca", None)]:
        conn.execute("insert into activity(pada, jenis, user_id, teks) values(?, 'contoh', ?, ?)", (sekarang, uid, teks))
    conn.close()
    print("data contoh dibuat di", s.root)


if __name__ == "__main__":
    asyncio.run(isi())
