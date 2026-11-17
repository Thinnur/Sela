# Sela: dokumen desain

Tanggal: 17 November 2026. Status: menunggu persetujuan Fathin.

Acuan:

- PRD v1.3: `/srv/hermes/data/outputs/private-comic-reader-prd/PRD-Reader-Pribadi-Fathin-Putri.md`.
- Mockup yang sudah disetujui Fathin: [`2026-11-17-sela-mockup.html`](2026-11-17-sela-mockup.html). Buka di browser.
- Bukti uji sumber dari Hermes: `/srv/hermes/data/outputs/comic-five-source-fulltest/`.

Kalau dokumen ini berbeda dengan PRD, dokumen ini yang berlaku. Untuk hal yang tidak dibahas di sini, PRD tetap jadi acuan, terutama bagian 10 (keamanan) dan 13 (acceptance criteria).

Penanda asal keputusan:

- **[Fathin]**: diputuskan Fathin.
- **[PRD]**: diambil dari PRD. Belum tentu sudah dikonfirmasi ulang.
- **[Claude]**: diputuskan Claude. Boleh diganti tanpa mengubah maksud produk.

## 1. Maksud

Fathin dan Putri ingin membaca komik berbahasa Indonesia dengan tenang, tanpa iklan, pop-up, redirect, dan tracker dari situs sumber. Mereka berbagi satu rak. Posisi baca, riwayat, status selesai, dan pengaturan baca dipisah per akun. Untuk menambah judul, cukup tempel link halaman judulnya. Selanjutnya sistem bekerja sendiri: semua chapter diunduh lalu disimpan di Google Drive, dan chapter baru ikut masuk saat terbit.

Judul pertama: *Money Keeps Piling Up No Matter How Much I Spend*, juga dikenal sebagai *Even If I Keep Spending, Money Keeps Piling Up*. Saat diuji, judul ini punya 26 chapter di Komiku. Fathin baru mulai membaca, jadi koleksi awalnya kecil. Meski begitu, rancangannya tidak boleh hanya cocok untuk satu judul.

Tampilan sama pentingnya dengan kelancaran. Aplikasi harus cantik dan ramah dipakai, baik di HP maupun desktop **[Fathin]**.

## 2. Tujuan versi pertama

1. Login Google. Hanya akun Fathin dan Putri yang boleh masuk.
2. Tambah judul: tempel link Komiku atau KomikIndo, lihat pratinjau, tekan Tambahkan, lalu semua chapter masuk antrean.
3. Setiap chapter diunduh, diverifikasi, dikemas jadi CBZ, diunggah ke Drive, lalu diverifikasi lagi. Baru setelah itu statusnya "siap".
4. Update dicek otomatis secara berkala. Bisa juga dicek manual.
5. Reader yang nyaman, dengan progres per akun yang tersinkron antarperangkat.
6. Tampilan mengikuti mockup, di HP maupun desktop.

## 3. Bukan tujuan versi pertama

- DeiManga atau API pihak ketiga lainnya. Chapter diambil langsung dari situs sumber **[Fathin]**.
- ManhwaIndo dan Komikcast, karena gambarnya ditolak 403. Juga BacaKomik, karena isinya identik dengan KomikIndo.
- Suwayomi.
- Notifikasi ke luar aplikasi (Telegram, WhatsApp, Discord), PWA offline, dan mode halaman atau RTL **[PRD]**.
- Pencarian katalog situs sumber dan impor massal.
- Menghapus judul atau arsip lewat UI. PRD belum memberi izin penghapusan. Kalau benar-benar perlu, Fathin menghapusnya manual **[Claude]**.

## 4. Anti-tujuan: tetap dianggap gagal walaupun aplikasinya jalan

- Menyentuh apa pun milik DiBeliin, sistem backup, rclone, atau token Hermes.
- Mengakali 403, CAPTCHA, atau challenge Cloudflare.
- Chapter berstatus "siap" padahal belum lolos verifikasi, atau CBZ setengah jadi terunggah sebagai arsip.
- Gambar atau arsip bisa dibuka tanpa login, atau browser masih meminta sesuatu ke CDN sumber saat membaca chapter yang sudah siap.
- Disk VPS terisi penuh.
- Progres satu orang menimpa progres orang lain, atau bisa dilihat orang lain.
- Satu chapter berisi gambar campuran dari dua situs.

## 5. Batasan

- Aplikasi berjalan di VPS produksi DiBeliin. Per 17 Nov 2026: 8 vCPU, RAM 7,8 GB (sekitar 2,4 GB yang masih tersedia), disk 58 GB dengan sisa 8,5 GB (86% terpakai).
- Python 3.12 dan Node 24 sudah terpasang. Cloudflare Tunnel dikelola dari dashboard, jadi Fathin yang menambahkan route.
- Kapasitas Drive 5 TB adalah informasi dari Fathin dan belum pernah dicek.
- Claude tidak menerima rahasia lewat chat. Fathin menempelkan sendiri client secret dan nilai rahasia lain ke berkas di server.
- Hanya konten yang publik tanpa login yang diambil. Proses berhenti kalau akses ditolak, dan kredit penerjemah di dalam gambar tidak dipotong.

## 6. Arsitektur

```text
Browser ──HTTPS──> Cloudflare Tunnel ──> 127.0.0.1:8095  sela.service (uvicorn, 1 proses)
                                           ├─ web: FastAPI + Jinja2
                                           ├─ worker: antrean unduh (asyncio)
                                           ├─ penjadwal: cek update, backup DB
                                           ├─ SQLite  /srv/sela/data/sela.db (WAL)
                                           ├─ cache   /srv/sela/cache  (CBZ, dibatasi)
                                           ├─ tmp     /srv/sela/tmp    (kerja unduh)
                                           ├─ ──> komiku.org, komikindo.ch + CDN-nya (httpx)
                                           └─ ──> Google Drive API (scope drive.file)
```

- Server memakai VPS, bukan Vercel **[Fathin]**. Alasannya, worker unduhan berjalan lama dan butuh disk serta SQLite.
- Stack **[Claude]**: Python 3.12, FastAPI, uvicorn, Jinja2, httpx, Authlib, Pillow, dan BeautifulSoup (parser bawaan `html.parser`, tanpa lxml). Pustaka standar dipakai untuk `sqlite3`, `zipfile`, dan `hashlib`. Tidak memakai Redis, Celery, Docker, React, atau proses build frontend.
- Web, worker, dan penjadwal berjalan dalam **satu proses** **[Claude]**. Antrean disimpan di SQLite. Saat start, job yang berstatus berjalan dikembalikan ke antrean sesuai checkpoint-nya.
- Port 8095 **[Claude]**. Builder perlu memastikan port ini belum dipakai.
- Frontend berupa HTML dari server dengan sedikit JavaScript biasa. Font Fredoka dan Nunito di-host sendiri (keduanya berlisensi OFL), supaya browser tidak mengirim request ke Google Fonts **[Claude]**.

## 7. Model data (SQLite)

Ini kebutuhan data, bukan skema final.

- **users**: id, google_sub (unik, terisi saat login pertama), email, nama, peran (`admin` untuk Fathin, `pembaca` untuk Putri), latar_reader (`gelap` atau `kertas`, bawaan `gelap`).
- **series**: id, judul, alias (JSON), sinopsis (teks polos), path sampul, jenis (manhwa, manga, dan seterusnya), ditambahkan_oleh, ditambahkan_pada.
- **series_sources**: id, series_id, adapter (`komiku` atau `komikindo`), url kanonis (unik), peran (`utama` atau `cadangan`), cek_terakhir, cek_sukses_terakhir, jenis_error_terakhir, pesan_error_terakhir, cek_berikutnya.
- **chapters**: id, series_id, label asli (misalnya "10.5"), label_normal (unik per series), kunci_urut, terbit_pada, status arsip (`antre`, `mengunduh`, `mengunggah`, `memverifikasi`, `siap`, `menunggu_ulang`, `gagal`, `menunggu_ruang`), jadi_siap_pada.
- **chapter_sources**: chapter_id, series_source_id, url chapter di sumber. Unik per pasangan (sumber, url).
- **archives**: chapter_id, drive_file_id, sumber yang dipakai, ukuran, md5, sha256, jumlah_gambar, manifest (JSON), diverifikasi_pada.
- **reading_progress**: kunci (user_id, series_id). Isinya chapter_id, indeks_gambar, fraksi (posisi di dalam gambar, 0 sampai 1), rev, diperbarui_pada.
- **chapter_reads**: kunci (user_id, chapter_id). Isinya status (`dibaca` atau `selesai`) dan diperbarui_pada.
- **series_visits**: kunci (user_id, series_id). Isinya terakhir_dibuka, dipakai untuk menghitung chapter "baru".
- **jobs**: id, jenis (`unduh_chapter`, `cek_update`, `backup_db`), target, status, percobaan, jalan_setelah, kunci_idem (unik), checkpoint (JSON), jenis_error, pesan_error.
- **activity**: kejadian bersama untuk panel Aktivitas. Isinya chapter baru ditemukan, unduhan selesai atau gagal, judul ditambahkan oleh siapa, dan sumber bermasalah. Kejadian membaca milik pasangan tidak dicatat di sini **[Claude]**.

Urutan chapter **[Claude]**:

- Kalau label mengandung angka, angka itu yang dipakai sebagai kunci urut.
- Kalau tidak ada angkanya (prolog, ekstra tanpa nomor), dipakai posisinya di daftar sumber utama.
- Label asli selalu disimpan dan ditampilkan apa adanya.

"Baru" artinya chapter berstatus siap, belum dibaca pengguna aktif, dan menjadi siap setelah pengguna itu terakhir membuka judulnya **[Claude]**.

## 8. Adapter sumber

Ada dua adapter sejak versi pertama: **Komiku** (sumber utama) dan **KomikIndo** (cadangan) **[Fathin]**. Masing-masing adalah modul kecil dengan fungsi berikut:

- `cocok(url)` dan `normalisasi(url)`.
- `ambil_judul(url)`, yang mengembalikan judul, alias, sinopsis, URL sampul, jenis, dan daftar chapter (label, URL, tanggal). Daftar chapter harus lengkap, termasuk kalau ada pagination.
- `ambil_gambar(url_chapter)`, yang mengembalikan URL gambar berurutan beserta header request yang sah (misalnya Referer halaman chapter).
- Kegagalan dilempar sebagai error berjenis `tidak_didukung`, `tidak_ada`, `berubah`, `ditolak`, `dibatasi`, atau `sementara`.

Fakta dari bukti uji Hermes:

- **Komiku**:
  - Halaman judul ada di `komiku.org/manga/<slug>`, dengan 26 link chapter dalam HTML.
  - Gambar ada di `img.komiku.org`. URL-nya berakhiran `.jpg`, padahal formatnya WEBP.
  - Chapter 1 berisi 146 gambar.
- **KomikIndo**:
  - Halaman judul ada di `komikindo.ch/komik/<slug>`, dan halaman chapter di `komikindo.ch/<slug>-chapter-N`.
  - Chapter 1 berisi 79 gambar JPEG yang tersebar di 5 host berbeda: `amatipolanyatirudesainnya.lol`, `bukansiapasiapa.lol`, `ss.guatauaslinyalusiapa.asia`, `ss.menjadimanusiaikan.asia`, dan `ss.rasainginberak.asia`.
  - Host gambar seperti ini kemungkinan besar sering berganti, jadi allowlist statis akan cepat usang.
- HTML chapter dari kedua situs tersimpan di folder bukti (`Komiku-chapter.html`, `KomikIndo_ch-chapter.html`) dan bisa dipakai sebagai fixture tes. HTML halaman judul belum tersimpan, jadi builder perlu mengambilnya sekali dan menyimpannya sebagai fixture.

Aturan host gambar **[Claude]**:

- Host halaman sumber selalu berasal dari allowlist statis: `komiku.org`, `img.komiku.org`, dan `komikindo.ch`.
- Host gambar boleh dipakai kalau tercantum di allowlist statis, **atau** muncul di HTML halaman chapter yang diambil dari host sumber yang ada di allowlist.
- Di luar itu, setiap request tetap harus lolos semua pemeriksaan SSRF:
  - Hanya HTTPS.
  - IP hasil resolve DNS harus publik.
  - Redirect diikuti manual, dan setiap tujuannya divalidasi ulang.
  - Isi respons benar-benar bisa di-decode sebagai gambar.
- Host gambar yang dipakai dicatat di manifest.

Etika request **[Claude]**:

- Sampai 3 chapter diproses bersamaan: diunduh, dikemas, dan diunggah **[Fathin: 3–4 chapter]**. Angka ini bisa dinaikkan ke 4 lewat setelan `SELA_CHAPTER_PARALEL` **[Claude: bawaan 3]**.
- Request gambar dibatasi per situs sumber, bukan per chapter. Paling banyak 8 request paralel ke satu situs, dibagi ke semua chapter yang sedang berjalan, termasuk semua host CDN situs itu **[Claude]**. Dengan begitu, menambah jumlah chapter paralel tidak melipatgandakan beban ke situs sumber.
- Kalau sebuah situs membalas 429 atau responsnya melambat drastis, worker turun ke 1 chapter untuk situs itu. Batas normal kembali berlaku setelah cek berikutnya berhasil **[Claude]**.
- Ada jeda kecil antar-request.
- User-Agent jujur, tidak menyamar. Kalau sumber menolak, proses berhenti dan melapor.

## 9. Alur unduh dan penyimpanan

```text
antre ─> mengunduh ─> mengunggah ─> memverifikasi ─> siap
            │             │              │
            └──── error ──┴──────────────┴─> menunggu_ulang ─(habis jatah)─> gagal
```

1. Worker mengambil satu job `unduh_chapter`.
2. Sebelum mulai, worker mengecek anggaran disk. Kalau `tmp` ditambah `cache` akan melebihi 1,5 GB **[Claude]**, atau sisa disk VPS di bawah 3 GB **[Claude]**, statusnya jadi `menunggu_ruang`.
3. Daftar gambar diambil dari adapter, lalu setiap gambar diunduh ke `/srv/sela/tmp/<job>/` dengan batasan:
   - Ukuran per gambar paling besar 20 MB, dan satu chapter paling banyak 600 gambar.
   - Pillow harus bisa mendekode setiap gambar. Di seluruh proses, paling banyak 2 gambar di-decode sekaligus, karena satu strip manhwa panjang bisa memakan puluhan MB RAM saat di-decode **[Claude]**.
   - Tipe file ditentukan dari isinya, bukan dari ekstensi URL.
   - Urutan gambar dipertahankan.
   - Gambar tidak dikompres ulang.
4. Satu gambar gagal artinya chapter belum lengkap. Tidak boleh ada CBZ yang terbit setengah jadi.
5. CBZ dibuat dengan mode ZIP tanpa kompresi (`ZIP_STORED`):
   - Nama entri `0001.webp`, `0002.jpg`, dan seterusnya, dengan ekstensi sesuai tipe asli gambar.
   - Ditambah `manifest.json` yang berisi, untuk setiap gambar: nomor urut, nama, MIME, lebar, tinggi, ukuran, sha256, dan host. Juga berisi info sumber dan versi Sela.
6. Sebelum mengunggah, worker mencari di Drive file milik Sela yang `appProperties.sela_chapter` sama dengan id chapter ini:
   - Kalau ada dan md5-nya cocok, file itu yang dipakai.
   - Kalau ada tapi md5-nya tidak cocok, unggah file baru. File lama tidak dihapus, hanya dicatat di log untuk ditinjau **[Claude]**.
7. Unggah memakai resumable upload ke `Sela/<judul> [<series_id>]/ch-<label>.cbz` dengan `appProperties` `{sela_chapter, sela_job}`. Nama file di Drive tidak dianggap unik.
8. Verifikasi: `size` dan `md5Checksum` dari Drive harus sama dengan file lokal. Selama pengujian implementasi, sebagian chapter juga diunduh ulang penuh dari Drive dan dicek.
9. Status diubah jadi `siap` dan kejadiannya dicatat di activity. Setelah itu, seluruh folder tmp chapter tersebut, termasuk CBZ-nya, langsung dihapus dari VPS **[Fathin]**. Cache baru terisi kalau chapter dibuka untuk dibaca. Begitu satu chapter selesai (siap atau gagal), slotnya langsung dipakai chapter berikutnya di antrean. Jadi di VPS hanya ada chapter yang sedang diproses, paling banyak 3–4 chapter. Puncak pemakaian disk sekitar 2 × ukuran chapter × jumlah chapter paralel, karena gambar dan CBZ sempat ada bersamaan sebelum dihapus. Untuk 4 chapter berukuran 15 MB, puncaknya sekitar 120 MB.
10. Kalau proses mati di tengah, job dilanjutkan dari checkpoint saat start. Kalau terputus setelah unggah, rekonsiliasi dulu lewat langkah 6.

Retry **[Claude]**:

- **`sementara`**: backoff 1 menit, 5 menit, 30 menit, lalu 2 jam. Setelah 5 percobaan, statusnya jadi `gagal`.
- **`dibatasi` (429)**: ikuti `Retry-After`, lalu backoff seperti `sementara`.
- **`ditolak` (403 atau challenge)**: tidak di-retry. Sumbernya ditandai bermasalah dan semua job dari sumber itu dijeda sampai ada yang menekan "Coba lagi".
- **`berubah`**: daftar chapter kosong atau menyusut tidak wajar, atau HTML tidak bisa di-parse. Ini ditandai sebagai anomali. Data lama tidak dihapus dan job tidak dibuat.

Cadangan KomikIndo **[Fathin: ada sejak versi pertama]**:

- **Saat menambah judul dari Komiku**, Sela mencoba URL KomikIndo dengan slug yang sama. Untuk judul uji, slug-nya memang sama. Kalau ditemukan, pratinjau menampilkan "Cadangan ditemukan: KomikIndo, N chapter" dengan centang untuk menautkannya. Kalau tidak ditemukan, link cadangan bisa ditempel manual dari menu halaman detail.
- **Sela tidak pernah pindah sumber sendiri.** Kalau satu chapter gagal dari Komiku atau Komiku ditandai `ditolak`, baris chapter itu menampilkan tombol "Ambil dari KomikIndo", asalkan cadangannya punya chapter dengan label_normal yang sama. Sekali tekan sudah dihitung sebagai konfirmasi. Seluruh chapter lalu diambil dari KomikIndo, dan arsipnya mencatat sumber itu. Di daftar chapter, chapter tersebut diberi tanda kecil "dari KomikIndo".
- **Kalau cek update ke Komiku gagal**, KomikIndo ikut dicek. Chapter yang hanya ditemukan di KomikIndo tampil dengan status "ada di KomikIndo" dan tombol yang sama.
- **Sumber utama sebuah judul bisa diganti** lewat menu detail, dengan konfirmasi **[Claude]**.

Cek update:

- Berjalan setiap 6 jam dengan jitter ±30 menit **[PRD, belum dikonfirmasi Fathin]**. Hanya satu job cek per judul.
- Tombol cek manual punya jeda 10 menit **[Claude]** dan tidak boleh membuat job ganda.
- Hanya chapter yang belum dikenal yang diantrekan.

## 10. Membaca

Penyajian:

- `GET /baca/<chapter_id>` menampilkan halaman reader.
- `GET /api/chapter/<id>/gambar/<n>` mengirim satu entri langsung dari CBZ yang ada di cache. Isi CBZ tidak diekstrak ke disk.
- Cache:
  - Lokasinya `/srv/sela/cache/<chapter_id>.cbz`, dengan batas 1 GB yang dihitung bersama tmp dalam anggaran 1,5 GB. Kalau penuh, file yang paling lama tidak dibuka dibuang lebih dulu (LRU) **[Claude]**.
  - Chapter yang dibuka dalam 30 menit terakhir tidak boleh dibuang.
- Pengambilan dari Drive (`files.get?alt=media`):
  - Kalau beberapa request meminta chapter yang sama, hanya satu unduhan yang berjalan, lewat kunci per chapter.
  - Saat pembaca melewati 50% chapter, chapter berikutnya diambil lebih dulu ke cache **[Claude]**.
- Chapter yang sudah ada di cache tetap bisa dibaca walaupun Drive atau sumber sedang mati.
- Header:
  - Gambar: `Cache-Control: private, max-age=86400`.
  - Semua halaman: CSP `default-src 'self'; img-src 'self' data:; frame-ancestors 'none'`, yang otomatis memblokir request ke CDN sumber.
  - Pastikan Cloudflare tidak meng-cache endpoint gambar.

Halaman reader:

- Setiap `<img>` diberi atribut `width` dan `height` dari manifest, supaya tata letak sudah stabil sebelum gambarnya termuat dan posisi baca bisa dipulihkan dengan tepat. Gambar dimuat dengan `loading="lazy"` dan `decoding="async"`.
- Gambar disusun tanpa jarak, supaya strip manhwa menyambung. Di desktop lebarnya paling besar 720 px dan diletakkan di tengah **[Claude]**. Di HP lebarnya penuh.
- Bilah atas dan bawah muncul saat bagian tengah layar diketuk.
  - Bilah atas: tombol kembali, judul seri, dan label chapter. Label chapter bisa diketuk untuk membuka lembar daftar chapter.
  - Bilah bawah: tombol chapter sebelumnya, slider posisi (berdasarkan indeks gambar), persentase, dan tombol chapter berikutnya. Di bawahnya ada tanda "Posisi tersimpan" dan tombol pengaturan.
- Pengaturan baca: pilihan latar **Gelap** atau **Kertas**, disimpan per akun di server **[Fathin]**. Pilihan ini ikut ke semua perangkat dan sudah diterapkan saat halaman dirender, jadi tidak ada kedipan. Akun yang belum pernah memilih memakai Gelap **[Claude]**.

Progres:

- Posisi disimpan sebagai (chapter_id, indeks_gambar, fraksi). Data dikirim paling sering tiap 5 detik selama menggulir, ditambah saat `visibilitychange` menjadi hidden (kalau ada guliran sejak simpanan terakhir) dan saat pindah chapter.
- Salinan disimpan di `localStorage` untuk berjaga kalau koneksi putus, lalu disinkronkan saat halaman dibuka lagi.
- Konflik antarperangkat diselesaikan dengan nomor revisi:
  - Klien mengirim `rev` yang terakhir ia ketahui. Server menyimpan kalau nilainya sama dengan revisi saat ini, lalu menaikkannya.
  - Kalau berbeda, server membalas 409 beserta posisi terbaru. Kalau halaman baru dibuka, klien menawarkan "Lanjut dari posisi di perangkat lain?". Kalau pengguna sedang aktif menggulir, klien memakai revisi baru itu dan melanjutkan.
  - Tab di latar belakang tidak pernah mengirim posisi tanpa ada guliran.
- Chapter otomatis ditandai selesai saat bagian bawah gambar terakhir terlihat (fraksi ≥ 0,95). Penanda ini bisa dibatalkan. Membaca ulang chapter lama tidak mengubah status chapter lain **[PRD]**.

Layar akhir chapter **[Fathin]**, sesuai mockup:

1. Kartu "Chapter N selesai" dengan tautan Batalkan.
2. Kartu chapter berikutnya dengan tombol besar "Lanjut chapter N+1". Kalau chapter itu belum siap, tombol diganti status dan persentase unduhannya.
3. Deret "Lompat ke chapter" berisi 5 petak: 2 chapter sebelum dan 3 sesudah chapter yang baru selesai.
   - Di dekat awal atau akhir seri, deretnya bergeser supaya tetap berisi 5. Misalnya di chapter 1 isinya chapter 2 sampai 6 **[Claude]**.
   - Ikon di petak: centang teal berarti selesai, titik koral berarti belum dibaca, ikon unduh berarti belum siap. Petak yang belum siap hanya menampilkan statusnya dan tidak membuka reader.
   - Tautan "Semua chapter" membuka lembar daftar chapter.
4. Tombol "Kembali ke detail judul".

## 11. Tampilan

Mockup yang sudah disetujui ada di `2026-11-17-sela-mockup.html`. Gayanya diturunkan dari referensi yang dipilih Fathin, yaitu UI toko buku bernuansa krem pastel dengan sampul buku ilustratif, lalu disesuaikan untuk manga dan manhwa.

Token warna:

| Nama | Hex | Dipakai untuk |
|---|---|---|
| Kertas | `#FBF6EE` | Latar panel utama |
| Pasir | `#EADFD2` | Bingkai luar, rail |
| Pasir muda | `#F1E7DA` | Kolom cari, kartu sekunder |
| Lavender | `#8B7FD0` | Elemen aktif, kartu lanjut baca, progres |
| Koral | `#EF6B5B` | Tombol aksi utama, penanda "baru" |
| Mustard | `#F2B544` | Pita pembatas (sedang dibaca) |
| Teal | `#4AA3A2` | Siap, selesai, sumber sehat |
| Navy | `#3E5C8A` | Aksen sekunder |
| Tinta | `#3B2F2A` | Teks utama |
| Reader gelap | `#2A211D` latar, `#3A2F2A` bilah | Latar reader Gelap |

- Teks kecil berwarna koral harus memenuhi kontras 4,5:1 terhadap latar. `#E0574A` di mockup belum cukup kontras, jadi gunakan koral yang lebih gelap, misalnya `#B8443A`, untuk teks di bawah 14 px.
- Huruf: Fredoka (500) untuk judul dan label tombol, Nunito (400, 700) untuk teks.

Komponen khas (dipakai secukupnya):

- **Sampul volume:** sudut 3/9 px, punggung buku lebih gelap di kiri, tepi halaman putih di bawah. Sampul memakai gambar dari sumber yang disimpan saat judul ditambahkan, dengan ukuran kecil, di disk VPS dan juga di folder Drive judul itu.
- **Pita mustard** menggantung di sampul judul yang sedang dibaca pengguna aktif. Pita ini milik masing-masing akun.
- **Screentone** (titik-titik halus) hanya dipakai di kartu "Lanjut baca".
- **Balon kata** hanya dipakai di panel Aktivitas.

Tata letak:

- **≥ 1100 px:**
  - Rail ikon di kiri, konten di tengah, panel Aktivitas di kanan.
  - Panel Aktivitas berisi kartu status sumber, kejadian dalam bentuk balon kata, dan kolom "Tempel link judul".
- **720–1099 px:** rail dan konten saja. Aktivitas dibuka lewat ikon lonceng.
- **< 720 px:**
  - Sapaan dan avatar di atas, lalu kolom cari dengan tombol tambah link.
  - Kartu Lanjut baca ada paling atas.
  - Di bawahnya chip pills yang bisa digeser dan grid sampul 3 kolom.
  - Navigasi bawah berisi Beranda, Rak, tombol + di tengah, Aktivitas, dan Akun.
- Tidak boleh ada scroll horizontal di lebar 360 px.

Halaman:

- **Masuk:** satu kalimat bahwa web ini pribadi, plus tombol Masuk dengan Google.
- **Beranda:**
  - Di desktop: rak bersama dengan chip filter berikon sampul mini, lalu kartu Lanjut baca dengan tiga status kecil (chapter siap, cek terakhir, isi Drive).
  - Di HP: Lanjut baca paling atas.
- **Rak:** semua judul, dengan filter Semua, Dibaca, Baru, Manhwa, Manga, Selesai.
- **Detail judul:**
  - Sampul besar, tag, judul, alias, dan sinopsis.
  - Tombol "Lanjut chapter N", "Dari chapter 1", cek update, dan menu.
  - Tiga angka: siap dari total, antre atau diunduh, dan gagal. Ditambah kartu sumber: Komiku utama dan KomikIndo cadangan, beserta waktu cek terakhir.
  - Daftar chapter dengan segmen Semua, Belum dibaca, dan Siap, serta urutan terbaru lebih dulu. Daftar ini punya dua kolom terpisah:
    - **Arsip** (berlaku untuk berdua): antre, mengunduh dengan persentase, gagal dengan alasannya dan tombol coba lagi, atau siap.
    - **Bacaanmu** (akun aktif): belum dibaca, sedang dibaca dengan persentase dan pita, atau selesai.
  - Label chapter ditampilkan apa adanya, dengan penanda "baru" atau "ekstra".
- **Reader:** lihat bagian 10.
- **Aktivitas:**
  - Kejadian bersama, unduhan yang sedang berjalan, kegagalan yang bisa dicoba ulang, status sumber, status Drive, dan pemakaian anggaran disk.
  - Tombol jeda dan lanjutkan antrean.
  - Data di-*polling* tiap 10 detik selama halaman terlihat, tanpa WebSocket **[Claude]**.
- **Akun:**
  - Nama, pilihan latar reader, dan tombol keluar.
  - Khusus Fathin: status Drive dan tombol Sambungkan Drive.
- **Tambah link:** lembar atau modal dengan langkah tempel URL, validasi di server, lalu pratinjau (sampul, judul, sumber, jumlah chapter yang benar-benar ditemukan, dan cadangan kalau ada), kemudian tombol Tambahkan. Kalau URL sudah ada, Sela langsung membuka judul yang sudah ada.

Gaya bahasa: bahasa Indonesia santai, sentence case, dan label tombol diawali kata kerja. Tombol di mockup polos tanpa gradasi. Gradasi pelangi dari referensi tidak dipakai **[Claude]**.

Aksesibilitas:

- Fokus keyboard terlihat.
- Animasi mengikuti `prefers-reduced-motion`.
- Target sentuh minimal 40 px.
- Ikon tanpa teks diberi `aria-label`.

## 12. Login, izin, dan Drive

Login:

- Login memakai Google OIDC lewat Authlib, dengan scope `openid email profile`.
- Allowlist diisi dari env `SELA_ALLOWED_EMAILS`, berisi dua email yang diisi Fathin saat deploy. Login pertama dari email yang ada di allowlist dan sudah diverifikasi Google akan mengikat `google_sub`. Setelah itu identitas dicocokkan dengan `sub` **[PRD]**. Akun lain mendapat halaman 403.
- Sesi berupa cookie bertanda tangan dengan atribut `Secure`, `HttpOnly`, dan `SameSite=Lax`, berlaku 30 hari **[Claude]**.
- Semua perubahan memakai POST dan wajib lolos pemeriksaan header `Origin`.
- Semua endpoint, termasuk sampul dan gambar, wajib punya sesi yang valid.

Peran **[PRD]**:

- Keduanya boleh menambah judul, cek update, mencoba ulang, dan mengambil dari cadangan.
- Hanya Fathin yang boleh menyambungkan Drive dan mengganti sumber utama.

Drive:

- Drive disambungkan lewat alur persetujuan terpisah di `/akun/drive`, khusus Fathin.
  - Scope-nya `drive.file`, dengan `access_type=offline` dan `prompt=consent`.
  - Refresh token disimpan di `/srv/sela/secrets/drive.json` (mode 600) dan tidak pernah ditulis ke log.
- Sela membuat folder `Sela` di root Drive. Dengan scope `drive.file`, Sela tidak bisa melihat folder backup sama sekali, jadi isolasi dari backup terjaga dengan sendirinya. Folder ini tidak dibagikan ke siapa pun. Putri membaca lewat backend, tanpa akses langsung ke Drive.
- OAuth client:
  - Dibuat di **project Google Cloud baru khusus Sela**, terpisah dari project Hermes yang dipakai rclone **[Claude, rekomendasi]**.
  - Jenisnya Web application, dengan redirect URI `https://<domain>/auth/callback` dan `https://<domain>/akun/drive/callback`.
- **Jebakan yang harus dihindari:**
  - Kalau consent screen masih berstatus *Testing*, refresh token untuk scope di luar nama, email, dan profil kedaluwarsa dalam 7 hari. Drive akan berhenti diam-diam setiap minggu. Status project harus *In production*.
  - Setahuku `drive.file` termasuk scope non-sensitif, jadi tidak perlu verifikasi Google. Builder perlu mengecek ulang kebijakan Google saat ini.
- Kalau token dicabut atau Drive membatasi request, unduhan berhenti dengan status yang jelas, tidak berputar ulang tanpa henti. Chapter yang sudah ada di cache tetap bisa dibaca.

## 13. Operasional

- Linux user `sela` tanpa shell login.
- Folder `/srv/sela/{app,data,cache,tmp,secrets}`, dengan venv di `/srv/sela/app/.venv`.
- `sela.service` (systemd) **[Claude]**:
  - Batas sumber daya: `MemoryMax=512M`, `CPUQuota=100%`, `Nice=10`, `IOSchedulingClass=idle`. Batas memori dibuat lebih longgar karena beberapa chapter diproses bersamaan.
  - Pengamanan: `NoNewPrivileges=yes`, `ProtectSystem=strict`, `ProtectHome=yes`, `PrivateTmp=yes`, dan `ReadWritePaths=/srv/sela/data /srv/sela/cache /srv/sela/tmp`.
  - Proses mendengarkan di `127.0.0.1:8095`.
- Fathin menambahkan route Cloudflare Tunnel dari dashboard: subdomain ke `http://127.0.0.1:8095`.
- Backup database Sela **[Claude]**:
  - Setiap hari dibuat salinan SQLite yang konsisten, lalu diunggah ke `Sela/_db/` di Drive. Simpan 14 salinan terakhir.
  - Backup ini memakai token Sela sendiri dan tidak menyentuh sistem backup VPS.
- Log ditulis ke journald dan sudah disanitasi: tanpa token dan tanpa URL bertanda tangan.
- Pemasangan di VPS produksi memerlukan persetujuan Fathin langkah demi langkah. Langkah yang dimaksud: membuat user, membuat unit systemd, dan menambah route tunnel.

## 14. Acceptance criteria

Kriteria 1 sampai 20 di PRD bagian 13 tetap berlaku. Kriteria 21 sampai 23 gugur karena tidak ada API pihak ketiga. Bagian SSRF dari kriteria 24 tetap berlaku. Kriteria tambahan:

- **A1. Latar per akun:** Fathin memilih Kertas di HP, lalu membuka laptop: latarnya Kertas. Putri tetap Gelap.
- **A2. Deret akhir chapter:**
  - Chapter 12 menampilkan 10.5, 11, 13, 14, 15.
  - Chapter 1 menampilkan 2 sampai 6.
  - Chapter terakhir menampilkan 5 chapter sebelumnya.
  - Ikon setiap petak sesuai status baca dan arsipnya.
- **A3. Cadangan:** kegagalan chapter dari Komiku memunculkan "Ambil dari KomikIndo" hanya kalau label yang sama ada di cadangan. Hasilnya satu chapter utuh dari KomikIndo dengan tanda sumbernya. Tanpa ditekan, Sela tidak pernah berpindah sumber.
- **A4. Host KomikIndo yang berganti** diterima hanya kalau muncul di halaman chapter. Host yang resolve ke IP privat ditolak.
- **A5. Tanpa request ke luar:** membaca chapter siap di browser menghasilkan nol request ke host selain domain Sela, dan nol pelanggaran CSP.
- **A6. Tampilan** sesuai mockup di lebar 390 px dan 1280 px, tanpa scroll horizontal di 360 px.
- **A7. Restart tanpa duplikat:** restart `sela.service` saat sedang mengunggah tidak menghasilkan CBZ ganda di Drive.
- **A8. Token Drive awet:** Drive masih berfungsi 8 hari setelah disambungkan. Ini membuktikan project sudah berstatus In production.
- **A9. Judul uji tuntas:** seluruh chapter judul uji siap dari Komiku, dan pemakaian disk Sela tetap di bawah anggaran sepanjang proses.
- **A10. Unduh paralel:**
  - Dengan 4 chapter paralel, request ke satu situs tidak pernah lebih dari 8 sekaligus, RAM proses tetap di bawah `MemoryMax`, dan tidak ada 429 pada pengaturan bawaan.
  - Setiap chapter yang sudah siap langsung hilang dari tmp.
  - Respons 429 dari fixture membuat worker turun ke 1 chapter.

## 15. Diserahkan ke builder

- Selector parser, penanganan pagination daftar chapter, dan regex normalisasi label.
- Struktur folder kode, nama modul, dan kerangka tes. Pakai pytest dengan fixture HTML dari bukti uji Hermes.
- CSS persisnya, struktur komponen, dan cara memuat ikon: Tabler self-host atau subset SVG.
- Angka-angka penyetelan (jeda, batas, interval) boleh disesuaikan berdasarkan pengukuran.

## 16. Masih terbuka

Butir di bawah ini perlu jawaban Fathin sebelum login dan deploy dikerjakan. Penyusunan rencana dan kode inti (adapter, unduhan, CBZ, reader) tidak perlu menunggu.

1. **Subdomain.** Usulannya `sela.akzara.id`. Dibutuhkan untuk redirect URI OAuth dan route tunnel.
2. **Project Google Cloud baru untuk Sela.** Langkahnya:
   1. Buat project-nya.
   2. Ubah consent screen ke status *In production*.
   3. Buat OAuth client berjenis Web application.
   4. Tempel sendiri client ID dan secret ke `/srv/sela/secrets/`.

   Claude bisa memandu langkah-langkahnya.
3. **Dua email yang diizinkan login.** Fathin mengisinya ke env saat deploy, tidak lewat chat.
4. **Perangkat Putri.** Perlu tahu jenis HP dan browsernya untuk uji kriteria 16 di PRD.
5. **Interval cek update.** Pakai 6 jam sampai Fathin menentukan lain.

Yang dicek builder sebelum judul pertama diimpor penuh: `robots.txt` dan ketentuan penggunaan Komiku serta KomikIndo. Hasilnya dilaporkan ke Fathin (lihat PRD bagian 4).
