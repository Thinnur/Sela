# Keputusan eksekusi Sela v1

Disalin dari ledger eksekusi (17–18 November 2026) sebelum ledger dihapus. Format setiap keputusan: apa yang diputuskan, alasannya, dan biayanya kalau ternyata keliru.

## Task yang selesai

- Task 1: complete (commits fbf459d..49f7a70, tests: uv run pytest tests/test_db.py -q → 4 passed in 0.46s)
- Task 2: complete (commits 49f7a70..dc7cd36, tests: uv run pytest tests/test_urutan.py -q → 3 passed in 0.02s)
- Task 3: complete (commits dc7cd36..73d9eec, tests: uv run pytest tests/test_fetch.py -q → 16 passed in 0.38s)
- Task 4: complete (commits 73d9eec..2294e19, tests: uv run pytest tests/test_komiku.py -q → 5 passed in 0.98s)
- Task 5: complete (commits 2294e19..74d96d6, tests: uv run pytest tests/test_komikindo.py -q → 3 passed in 0.83s)
- Task 6: complete (commits 74d96d6..3ab1a15, tests: uv run pytest tests/test_cbz.py -q → 8 passed in 0.38s)
- Task 7: complete (commits 3ab1a15..cda0060, tests: uv run pytest tests/test_drive.py -q → 7 passed in 0.26s)
- Task 8: complete (commits cda0060..8d0b36e, tests: uv run pytest tests/test_tambah.py -q → 5 passed in 1.94s)
- Task 9: complete (commits 8d0b36e..465a50a, tests: uv run pytest tests/test_proses.py -q → 6 passed in 3.07s)
- Task 10: complete (commits 465a50a..0fd4743, tests: uv run pytest tests/test_worker.py -q → 13 passed in 5.38s)
- Task 11: complete (commits 0fd4743..e695282, tests: uv run pytest tests/test_pembaru.py tests/test_tambah.py -q → 16 passed in 7.13s)
- Task 12: complete (commits e695282..b827111, tests: uv run pytest tests/test_progres.py -q → 6 passed in 1.64s)
- Task 13: complete (commits b827111..f7e224d, tests: uv run pytest tests/test_cache.py -q → 6 passed in 0.41s)
- Task 14: complete (commits f7e224d..71cb979, tests: uv run pytest tests/test_auth.py -q → 11 passed in 5.17s)
- Task 15: complete (commits 71cb979..3f2c935, tests: uv run pytest tests/test_api.py tests/test_auth.py -q → 22 passed in 10.69s)
- Task 16: complete (commits 3f2c935..0bb1e56, tests: uv run pytest tests/test_halaman.py -q → 16 passed in 12.30s)
- Task 17: complete (commits 0bb1e56..5330705, tests: uv run pytest tests/test_baca.py tests/test_api.py -q → 21 passed in 14.80s)
- Task 18: complete (commits 5330705..2e1299f, tests: uv run pytest -q → 146 passed in 45.52s)

## Keputusan yang diambil saat eksekusi

- Ruling: tanpa git worktree, pakai branch sela-v1 di checkout ini — repo baru tanpa commit, worktree tidak menambah isolasi berarti — biaya jika salah: kecil
- - T9 <- T7: tes memakai DriveLokal.berkas(id) dan .jumlah() yang tidak ada di Produces T7. Ruling: tambahkan dua helper itu di DriveLokal — dibutuhkan tes T9 — biaya: dua method kecil
- - T10 <- T11: Worker.jalan memanggil pembaru.detak padahal pembaru dibuat di T11. Ruling: Worker menerima parameter detak (callable|None), disambung di T18 — urutan task — biaya: satu parameter
- - T11 -> Worker.normalkan_situs: detak tidak memegang worker. Ruling: detak mengembalikan set situs yang ceknya sukses; Worker memanggil normalkan_situs — biaya: kecil
- - T1 conftest: ENV root /tmp/sela-uji. Ruling: fixture setelan memakai tmp_path sebagai root — isolasi tes — biaya: nihil
- Task 1: Ruling: tambah db.transaksi, kv_ambil, kv_set, dan validasi admin ada di allowlist — dipakai task berikutnya (kv, transaksi di T8/T9) — biaya: kecil
- Task 3: Ruling: ambil() mengembalikan dataclass Respons(url, headers, content, .text), bukan httpx.Response — body sudah di-decode stream sehingga header content-encoding membuat httpx.Response ganda-decode — biaya: konsumen pakai .content/.text yang sama
- Task 4: Ruling: tes judul Komiku memakai 27 chapter, bukan 26 — chapter 27 terbit 17 Nov 2026 saat fixture diambil — biaya: nihil
- Task 4: Ruling: tambah thumbnail.komiku.org ke HOST_STATIS — sampul Komiku ada di host itu — biaya: satu host statis
- Task 6: Ruling: batas 100 juta piksel dicek eksplisit dari header (lebar*tinggi) sebelum decode, bukan lewat Image.MAX_IMAGE_PIXELS global — Pillow hanya memberi warning di rentang 1x-2x batas, padahal gambar sebesar itu bisa melampaui MemoryMax — biaya: nihil
- Task 7: Ruling: DriveLokal mendapat helper berkas(), jumlah(), semua(), gagal_unduh, jumlah_unduh — dibutuhkan tes T9/T13/T18 — biaya: kode tes di modul produksi (kecil)
- Task 8: Ruling: tes memakai 27 chapter Komiku dan 27+26 chapter_sources — Komiku sudah merilis chapter 27, KomikIndo belum — biaya: nihil
- Task 8: Ruling: label yang hanya ada di cadangan saat judul ditambahkan juga jadi chapter 'hanya_cadangan' (fungsi sisipkan_chapter_cadangan dipakai ulang T11) — konsisten dengan spec bagian 9 — biaya: kecil
- Task 8: Ruling: tambahkan() menerima interval (bawaan 21600) untuk cek_berikutnya pertama — tambahkan tidak memegang Setelan — biaya: satu parameter
- Task 9: Ruling: tmp dibersihkan bila gagal sebelum CBZ jadi (gambar mentah tidak ditumpuk untuk retry); CBZ yang sudah jadi tetap disimpan bila unggah gagal (sesuai spec) — hemat anggaran disk — biaya: unduh ulang gambar saat retry
- Task 9: Ruling: satu gambar gagal membatalkan unduhan gambar lain di chapter itu (tes test_gambar_rusak_membatalkan_unduhan_lain) — tidak membuang slot request situs — biaya: nihil
- Task 9: Ruling: tambah cbz.hasil_dari(path) untuk melanjutkan dari CBZ yang sudah ada setelah crash — biaya: nihil
- Task 10: Ruling: SumberError tidak_ada/berubah/tidak_didukung pada job chapter langsung gagal tanpa retry — retry tidak akan mengubah hasil — biaya: pengguna menekan Coba lagi
- Task 10: Ruling: Worker menerima detak() async tanpa argumen yang mengembalikan set situs sehat; disambung di main (T18) — sesuai pre-flight — biaya: nihil
- Task 11: Ruling: cek_sumber tidak melempar SumberError; kegagalan dicatat di series_sources dan dikembalikan sebagai HasilCek.anomali — detak cukup memeriksa satu nilai — biaya: nihil
- Task 11: Ruling: ganti_sumber_utama juga mengantrekan ulang chapter yang belum siap dari sumber utama baru (bukan hanya membatalkan job lama) — tanpa ini chapter tersebut macet — biaya: unduhan dari sumber baru
- Task 14: Ruling: sesi dan Origin dijaga lewat middleware untuk semua rute (kecuali /masuk, /auth/callback, /static, /dev/masuk), bukan dependency per rute — rute baru otomatis terlindungi, dan tes rute yang belum ada tetap 401/403 — biaya: nihil
- Task 14: Ruling: Setelan menambah google_client_id/secret dari env SELA_GOOGLE_CLIENT_ID/SECRET; /keluar memakai POST — biaya: nihil
- Task 14: Ruling: login lewat sub yang sudah terikat tidak lagi mewajibkan email ada di allowlist (sesuai spec: email bisa berubah) — biaya: nihil
- Task 15: Ruling: rute API ditaruh di sela/api.py (pasang_api dipanggil buat_app), bukan langsung di web.py — web.py tetap kecil — biaya: nihil
- Task 15: Ruling: pratinjau tidak mengembalikan sampul_url — CSP img-src 'self' memblokir gambar dari sumber, jadi sampul baru tampil setelah judul ditambahkan dan disimpan — biaya: pratinjau tanpa gambar sampul
- Task 15: Ruling: tes "/akun/drive hanya admin" dipindah ke Task 18; di sini diuji lewat /api/series/{id}/sumber-utama (403 untuk pembaca) — biaya: nihil
- Task 16: Ruling: chip Manhua ditambahkan (judul pertama bertipe manhua di Komiku); filter "Selesai" = semua chapter siap sudah kamu tamatkan (status tamat/berlanjut seri tidak diparse) — biaya: label chip
- Task 16: Ruling: tombol "cek update" di rail memakai endpoint baru POST /api/cek-semua (minta_cek_manual untuk tiap judul, tetap kena cooldown) — mockup punya tombol itu — biaya: satu endpoint kecil
- Task 16: Ruling: data halaman dihitung di modul baru sela/tampilan.py; sela/main.py dibuat lebih awal (dev + DriveLokal lewat SELA_DRIVE_LOKAL=1) supaya cek visual bisa jalan; backup dan sambung Drive tetap di T18 — biaya: nihil
- Task 16: Ruling: progres memakai elemen <progress>, bukan style inline — CSP default-src 'self' memblokir atribut style; dijaga tes test_patuh_csp_tanpa_inline — biaya: nihil
- Task 17: Ruling: tambah GET /api/progres/{series_id}; reader mengecek posisi server saat tab kembali terlihat dan menawarkan posisi perangkat lain yang lebih baru (tanpa ini tab lama bisa menimpa progres HP lain diam-diam saat digulir lagi, bertentangan dengan PRD 5.5) — biaya: satu request ringan per kembali ke tab
- Task 17: Ruling: chapter yang dibuka tanpa posisi tersimpan langsung dicatat sebagai posisi terakhir (indeks 0) supaya "Lanjut baca" mengikuti chapter yang baru dibuka — biaya: satu simpanan saat buka
- Task 17: Ruling: lompatan posisi otomatis saat memuat tidak dihitung sebagai guliran pengguna — biaya: nihil
- Task 18: Ruling: nama backup memakai jam WIB (sela-YYYYMMDD-HHMM.db) supaya dua backup di hari yang sama tidak bentrok, dan diurutkan lewat nama — biaya: nihil
- Task 18: Ruling: alur sambung Drive meminta scope "openid email drive.file" (bukan drive.file saja) supaya Authlib bisa memverifikasi id_token — biaya: dua scope dasar tambahan
- Final: Ruling: DNS rebinding di _cek_ip — tetap shortcut berlabel; TLS memverifikasi host — biaya: SSRF lewat rebinding masih teoretis
- Final: Ruling: NAT64 64:ff9b::/96 dianggap global — VPS tanpa NAT64 — biaya: kecil
- Final: Ruling: gambar placeholder sah ikut terkemas — tidak bisa dibedakan dari isi; kredit dipertahankan sesuai spec — biaya: halaman ekstra di arsip
- Final: Ruling: perilaku Drive nyata belum diuji — diuji saat pemasangan (A7/A9, PASANG.md langkah 6-7) — biaya: bug Drive baru ketahuan saat pasang
- Final: Ruling: A6 visual — sudah dicek playwright oleh executor — biaya: nihil
- Final: Ruling: pratinjau tanpa sampul — tetap (CSP) — biaya: nihil
- Final: Ruling: ReadWritePaths memuat /srv/sela/secrets — perlu untuk drive.json — biaya: nihil
- Final: Ruling: User-Agent Sela/1.0 — format bot jujur — biaya: nihil
- Final: Ruling: CBZ cache dari Drive tidak dicek ulang md5 — Drive sudah diverifikasi saat unggah — biaya: arsip rusak di Drive tidak terdeteksi saat baca
- Final: Ruling: restore backup memicu unggah ulang — diizinkan spec — biaya: berkas ganda di Drive
- Final: Ruling: dependensi tanpa pin di pyproject — uv.lock mengunci — biaya: nihil
- Final: Ruling: angka ringkasan detail dihitung setelah saringan — nuansa UI — biaya: angka berubah saat menyaring

## Perbaikan dari review akhir

Reviewer baru (Opus) menemukan 0 Critical, 6 Important, dan 9 Minor. Tiga temuan Minor dinaikkan jadi Important karena langsung mengenai janji di spec.

- fixed duplikat/stale job per chapter (Important 1) — test_klaim_lewati_chapter_yang_sedang_diproses, test_coba_lagi_hanya_job_terbaru, test_chapter_sudah_siap_tidak_diproses_ulang, test_ambil_cadangan_membatalkan_job_lain, test_ganti_sumber_lewati_chapter_yang_berjalan RED→GREEN
- fixed deduplikasi URL/fragmen (Important 2) — test_url_sama_label_beda_jadi_satu RED→GREEN, test_cek_url_ganda_tidak_membuat_chapter_tanpa_sumber (penjaga)
- fixed URL/kode di log (Important 3) — test_log_tidak_memuat_url_dan_kode RED→GREEN (httpx/httpcore WARNING, uvicorn --no-access-log)
- fixed Drive dibatasi tidak menjeda antrean (Important 4) — test_drive_dibatasi_menjeda_antrean RED→GREEN (jeda 300 dtk via kv drive_jeda_sampai, percobaan tidak naik)
- fixed tanpa jeda antar-request (Important 5) — test_jeda_antar_request_per_situs, test_timeout_ditandai_lambat, test_timeout_menurunkan_situs RED→GREEN (jeda 0,25 dtk per slot; timeout dianggap lambat dan menurunkan situs ke 1 chapter)
- fixed batas decode dan crash loop (Important 6) — test_batas_piksel_muat_di_memori, test_mati_berulang_saat_diproses_akhirnya_gagal RED→GREEN (MAKS_PIKSEL 25 juta; pulihkan menghitung percobaan)
- fixed hapus email dari allowlist tidak mencabut akses (Minor 13 dinaikkan) — test_email_dihapus_dari_allowlist_mencabut_akses RED→GREEN (login lewat sub dan sesi lama dicek terhadap email asal di allowlist)
- fixed cadangan saat sumber utama ditolak (Minor 10 sebagian, dinaikkan) — test_sumber_ditolak_tawarkan_cadangan, test_sumber_ditolak_tidak_dicek_dan_tidak_dipulihkan_otomatis RED→GREEN, suite 167/167
- fixed 409 tanpa guliran lalu pagehide menimpa posisi (Minor 12 sebagian, dinaikkan) — tests/e2e/konflik-pagehide.sh RED (3,7)→(6,8) → GREEN (3,8) tetap; e2e reader.sh ulang 9/9 lulus dengan server terbaru; suite 167/167

## Temuan Minor yang ditunda

- tmp bocor — job gagal setelah CBZ jadi menyisakan tmp/<job>/ch.cbz; crash antara simpan arsip dan rmtree menyisakan folder; ch.cbz rusak saat dilanjutkan tidak dihapus sehingga Coba lagi tidak bisa memulihkan
- ENOSPC mengantre ulang dengan jalan_setelah=0 (bisa berulang tiap 2 dtk bila inode habis); "database or disk is full" SQLite tidak dianggap ENOSPC
- unggahan pertama paralel untuk satu judul bisa membuat folder Sela/judul ganda di Drive; ID folder di kv tidak dicek ulang bila foldernya dihapus
- setelah ganti sumber utama, chapter yang hanya ada di sumber lama tetap Antre
- normalisasi_label mengambil angka pertama ("Season 2 Chapter 5" jadi "2") dan bisa menggabungkan chapter berbeda
- setelah sesi habis, login selalu ke beranda; posisi lokal baru terkirim saat chapter yang sama dibuka lagi
- 500 yang bisa dihindari — /baca untuk chapter hanya_cadangan, 409 tanpa baris progres (vars(None)), /selesai untuk id tak dikenal
- kerja yang memblokir event loop — baca_entri di endpoint gambar, periksa_gambar di simpan_sampul, salinan backup SQLite, detak dijalankan di dalam putaran worker
