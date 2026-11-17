# Uji e2e reader

Jalankan server dev dengan data contoh, lalu `tests/e2e/reader.sh`. Skrip ini memakai `playwright-cli` (Chromium bawaan) pada lebar 390 px.

```bash
set -a; . <berkas env dev>; set +a   # SELA_ROOT, SELA_DEV_LOGIN=1, SELA_DRIVE_LOKAL=1, SELA_BASE_URL=http://localhost:8095
uv run python -m sela.contoh
uv run uvicorn sela.main:app --host 127.0.0.1 --port 8095
```

## Hasil 17–18 November 2026

| Langkah | Diharapkan | Hasil |
|---|---|---|
| 1. Buka chapter yang punya posisi tersimpan | Kembali ke gambar ke-2, fraksi 0,40 | `1:0.40` ✅ |
| 2. Gulir, tunggu 6 detik | Posisi masuk DB dengan rev naik | `(3, 3, 0.72, 2)`, sama dengan layar ✅ |
| 3. Muat ulang | Posisi sama | `3:0.72` ✅ |
| 4. Gulir sampai akhir | `chapter_reads` = selesai, kartu selesai tampil | `selesai`, kartu tampil ✅ |
| 5. Request jaringan | Hanya host Sela, tanpa pelanggaran CSP | hanya `http://localhost:8095`, konsol 0 galat ✅ |
| 6. Perangkat lain menyimpan, tab ini terlihat lagi | Muncul tawaran "Lanjut dari sana" | tampil ✅ |
| 7. Cookie dihapus lalu menggulir | Muncul tautan "Masuk lagi", posisi tersimpan di localStorage | tampil, `menunggu: true` ✅ |
| 7b. Masuk lagi lalu buka chapter itu | Posisi lokal terkirim ke server | `(5, 1)` ✅ |
| 9. Respons 409 sebelum menggulir, lalu tab ditutup (`konflik-pagehide.sh`) | Posisi dari perangkat lain tidak tertimpa | sebelum perbaikan tertimpa jadi `(6, 8)`, sesudah perbaikan tetap `(3, 8)` ✅ |
| 8. Pilih latar Kertas, lalu muat ulang | Kelas `latar-kertas` bertahan | ✅ |

Langkah 6 disimulasikan dengan POST dari konteks halaman dan event `visibilitychange`, bukan dengan dua perangkat sungguhan.
