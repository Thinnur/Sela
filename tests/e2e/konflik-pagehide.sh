#!/usr/bin/env bash
# Reader menerima 409 sebelum pengguna menggulir, lalu tab ditutup (pagehide).
# Harapan: posisi dari perangkat lain TIDAK ditimpa. Jalankan dengan server dev seperti tests/e2e/reader.md.
set -u
B=http://localhost:8095
DB=${SELA_DB:-/root/kerja/Sela/var/dev/data/sela.db}
pw() { timeout 60 playwright-cli -s=f7 "$@" >/dev/null 2>&1; }
ev() { timeout 60 playwright-cli -s=f7 --raw eval "$1" 2>/dev/null | tail -1; }
q() { python3 -I -c "import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute(sys.argv[2]).fetchone())" "$DB" "$1"; }
tunggu() { ev "new Promise(r => setTimeout(() => r('ok'), $1))" >/dev/null; }

read -r C R <<<"$(python3 -I -c "import sqlite3,sys; print(*sqlite3.connect(sys.argv[1]).execute('select chapter_id, rev from reading_progress where user_id=1 and series_id=1').fetchone())" "$DB")"
X=$(python3 -I -c "import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute('select id from chapters where series_id=1 and status=\"siap\" and id != ? order by id desc limit 1', (int(sys.argv[2]),)).fetchone()[0])" "$DB" "$C")
echo "sebelum: chapter=$C rev=$R, buka chapter $X"

timeout 90 playwright-cli -s=f7 --config "$HOME/.playwright/cli.config.json" open "$B/dev/masuk/1" >/dev/null 2>&1
pw resize 390 844
pw route "**/api/progres" --status=409 --body="{\"posisi\":{\"chapter_id\":$C,\"indeks\":1,\"fraksi\":0.5,\"rev\":$R}}"
pw goto "$B/baca/$X"
tunggu 1000
echo "tawaran tampil: $(ev '!document.querySelector("#tawaran").hidden')"
pw unroute "**/api/progres"
ev 'window.dispatchEvent(new Event("pagehide"))' >/dev/null
tunggu 1000
echo "sesudah: $(q 'select chapter_id, rev from reading_progress where user_id=1 and series_id=1')"
timeout 30 playwright-cli -s=f7 close >/dev/null 2>&1
