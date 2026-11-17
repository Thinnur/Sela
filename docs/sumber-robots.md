# Sumber: robots.txt dan ketentuan

Dicek 17 November 2026, sebelum judul pertama diimpor penuh (spec bagian 16, PRD bagian 4).

## Komiku (komiku.org)

```text
User-agent: *
Disallow: /wp-admin/
Allow: /wp-admin/admin-ajax.php
Sitemap: https://komiku.org/sitemapL5yutt5/chapter/
Sitemap: https://komiku.org/sitemapL5yutt5/series/
```

Path yang dipakai Sela (`/manga/<slug>/`, halaman chapter, dan `img.komiku.org`) tidak dilarang. Tautan halaman ketentuan penggunaan tidak ditemukan di robots.txt.

## KomikIndo (komikindo.ch)

Robots.txt dikelola Cloudflare:

- `User-agent: *` diberi `Allow: /` dengan `Content-Signal: search=yes,ai-train=no,use=reference`.
- Crawler pelatihan AI (GPTBot, ClaudeBot, CCBot, dan lain-lain) diblokir penuh.

Sela tidak memakai konten untuk pelatihan atau masukan AI. Sela hanya membaca halaman untuk arsip pribadi dua orang, dan User-Agent-nya jujur (`Sela/1.0; pembaca pribadi`). Path halaman judul dan chapter tidak dilarang untuk `*`.

## Catatan

- Robots.txt tidak sama dengan izin hak cipta. Seperti yang tertulis di PRD, penggunaan pribadi tidak menjadi jaminan legal.
- Kalau sumber menolak akses (403 atau challenge), Sela berhenti dan melaporkannya. Penolakan itu tidak diakali.
