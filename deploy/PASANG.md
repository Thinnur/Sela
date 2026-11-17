# Memasang Sela di VPS

Setiap langkah di bawah dijalankan hanya setelah Fathin menyetujuinya. Langkah-langkah ini tidak menyentuh DiBeliin, rclone, backup VPS, atau token Hermes.

## 0. Yang perlu disiapkan Fathin

1. **Subdomain**, misalnya `sela.akzara.id`.
2. **Project Google Cloud baru khusus Sela.** Jangan pakai project Hermes atau rclone.
   - OAuth consent screen: External, lalu ubah status ke **In production**. Kalau masih Testing, refresh token Drive kedaluwarsa setelah 7 hari.
   - Scope: `openid`, `email`, `profile`, `https://www.googleapis.com/auth/drive.file`.
   - Buat OAuth client berjenis **Web application**, dengan redirect URI:
     - `https://<subdomain>/auth/callback`
     - `https://<subdomain>/akun/drive/callback`
3. **Dua email Google** yang boleh masuk. Email Fathin menjadi admin.

## 1. User dan folder

```bash
useradd --system --home /srv/sela --shell /usr/sbin/nologin sela
mkdir -p /srv/sela/{app,data,cache,tmp,secrets}
chown -R sela:sela /srv/sela
chmod 700 /srv/sela/secrets
```

## 2. Kode dan venv

```bash
git clone /root/kerja/Sela /srv/sela/app    # atau salin isi branch sela-v1
cd /srv/sela/app && uv sync --no-dev
chown -R sela:sela /srv/sela/app
```

## 3. Rahasia (diisi Fathin sendiri, jangan lewat chat)

Buat `/srv/sela/secrets/sela.env` dengan mode 600 dan pemilik `sela`:

```text
SELA_ROOT=/srv/sela
SELA_ALLOWED_EMAILS=<email-fathin>,<email-putri>
SELA_ADMIN_EMAIL=<email-fathin>
SELA_BASE_URL=https://<subdomain>
SELA_SESSION_SECRET=<hasil: python3 -c "import secrets; print(secrets.token_urlsafe(48))">
SELA_GOOGLE_CLIENT_ID=<client id>
SELA_GOOGLE_CLIENT_SECRET=<client secret>
```

Karena `SELA_ROOT=/srv/sela`, Sela memakai `/srv/sela/data`, `/srv/sela/cache`, `/srv/sela/tmp`, dan `/srv/sela/secrets`.

## 4. Service

```bash
cp /srv/sela/app/deploy/sela.service /etc/systemd/system/sela.service
systemctl daemon-reload && systemctl enable --now sela
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8095/masuk    # harus 200
systemctl show sela -p MemoryMax                                        # harus 536870912
```

## 5. Cloudflare Tunnel (Fathin, lewat dashboard)

Tambahkan public hostname `<subdomain>` yang mengarah ke `http://127.0.0.1:8095`. Jangan pasang aturan cache untuk hostname ini.

## 6. Sambungkan Drive

Fathin login, buka **Akun**, lalu pilih **Sambungkan Drive**. Pastikan akun Google yang dipilih adalah akun Drive 5 TB. Sela akan membuat folder `Sela` di root Drive itu.

## 7. Judul pertama dan uji penerimaan

Tambahkan judul uji dari Komiku, lalu catat bukti A1–A10 di `docs/superpowers/bukti/`. A8 (token masih hidup setelah 8 hari) baru bisa dicek 8 hari setelah Drive tersambung.

## Kembali ke keadaan semula

```bash
systemctl disable --now sela && rm /etc/systemd/system/sela.service && systemctl daemon-reload
```

Hapus juga route tunnel di dashboard. Folder `Sela` di Drive tidak terhapus dengan sendirinya.
