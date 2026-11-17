#!/usr/bin/env bash
# Uji e2e reader Sela di server dev (localhost:8095) dengan playwright-cli.
set -u
cd "$(dirname "$0")"
B=http://localhost:8095
DB=/root/kerja/Sela/var/dev/data/sela.db
pw() { timeout 60 playwright-cli -s=e2e "$@" >/dev/null 2>&1; }
ev() { timeout 60 playwright-cli -s=e2e --raw eval "$1" 2>/dev/null | tail -1; }
q() { python3 -I -c "import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute(sys.argv[2]).fetchall())" "$DB" "$1"; }
tunggu() { ev "new Promise(r => setTimeout(() => r('ok'), $1))" >/dev/null; }
POS='(() => { const imgs=[...document.querySelectorAll(".strip img")]; const g=innerHeight*0.3; for (let i=0;i<imgs.length;i++){ const r=imgs[i].getBoundingClientRect(); if (r.bottom>g) return i+":"+((g-r.top)/r.height).toFixed(2); } return "akhir"; })()'

timeout 90 playwright-cli -s=e2e --config "$HOME/.playwright/cli.config.json" open "$B/dev/masuk/1" >/dev/null 2>&1
pw resize 390 844
pw goto "$B/baca/3"
tunggu 800
echo "1. posisi dipulihkan (harap 1:0.40): $(ev "$POS")"
pw screenshot --filename=reader-390-bilah.png

pw mousewheel 0 1400
tunggu 6500
echo "2. tersimpan setelah 5 detik: $(q 'select chapter_id, indeks, round(fraksi,2), rev from reading_progress where user_id=1 and series_id=1')  layar=$(ev "$POS")"

pw reload
tunggu 800
echo "3. setelah muat ulang: $(ev "$POS")"

ev 'window.scrollTo(0, document.body.scrollHeight)' >/dev/null
tunggu 1500
echo "4. selesai: db=$(q 'select status from chapter_reads where user_id=1 and chapter_id=3') kartu=$(ev '!document.querySelector("#kartu-selesai").hidden')"
pw screenshot --filename=reader-390-akhir.png

echo "5. host request: $(timeout 60 playwright-cli -s=e2e requests 2>/dev/null | grep -oE 'https?://[^/ ]+' | sort -u | tr '\n' ' ')"
echo "   galat konsol: $(timeout 60 playwright-cli -s=e2e console error 2>/dev/null | grep -c -iE 'error|refused|violat') baris"

REV=$(python3 -I -c "import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute('select rev from reading_progress where user_id=1 and series_id=1').fetchone()[0])" "$DB")
ev "fetch('/api/progres',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({series_id:1,chapter_id:4,indeks:2,fraksi:0.1,rev:$REV})}).then(r=>r.status)" >/dev/null
ev 'document.dispatchEvent(new Event("visibilitychange"))' >/dev/null
tunggu 800
echo "6. tawaran perangkat lain muncul: $(ev '!document.querySelector("#tawaran").hidden')"

pw goto "$B/baca/5"
tunggu 800
pw cookie-clear
pw mousewheel 0 900
tunggu 6500
echo "7. sesi habis: tautan masuk=$(ev '!document.querySelector("#masuk-lagi").hidden') lokal=$(ev 'localStorage.getItem("sela:pos:1")')"

pw goto "$B/dev/masuk/1"
pw goto "$B/baca/5"
tunggu 1500
echo "   setelah masuk lagi, posisi lokal terkirim: $(q 'select chapter_id, indeks from reading_progress where user_id=1 and series_id=1')"

pw click '#buka-pengaturan'
pw click '[data-latar="kertas"]'
tunggu 500
pw reload
echo "8. latar setelah muat ulang: $(ev 'document.body.className')"
pw screenshot --filename=reader-390-kertas.png
pw click '#buka-pengaturan'
pw click '[data-latar="gelap"]'
timeout 30 playwright-cli -s=e2e close >/dev/null 2>&1
