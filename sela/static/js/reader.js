"use strict";
(() => {
  const $ = (s) => document.querySelector(s);
  const R = $("#reader");
  const imgs = [...document.querySelectorAll(".strip img")];
  const series = R.dataset.series, chapter = Number(R.dataset.chapter);
  const KUNCI = `sela:pos:${series}`;
  const JEDA_SIMPAN = 5000;
  let rev = Number(R.dataset.rev);
  let bergerak = false, berubah = false, terakhirKirim = 0, jadwal = null, prefetchDikirim = false;
  let sudahSelesai = R.dataset.selesai === "1", selesaiDibatalkan = false, sedangKirim = false;

  const garis = () => window.innerHeight * 0.3; // garis baca: 30% dari atas layar

  function posisiSekarang() {
    if (!imgs.length) return { indeks: 0, fraksi: 0 };
    const g = garis();
    for (let i = 0; i < imgs.length; i++) {
      const r = imgs[i].getBoundingClientRect();
      if (r.bottom > g) return { indeks: i, fraksi: Math.min(1, Math.max(0, (g - r.top) / r.height)) };
    }
    return { indeks: imgs.length - 1, fraksi: 1 };
  }

  let abaikanScroll = false;
  function lompatKe(indeks, fraksi) {
    const img = imgs[indeks];
    if (!img) return;
    const r = img.getBoundingClientRect();
    abaikanScroll = true;  // lompatan otomatis bukan guliran pengguna
    window.scrollTo(0, window.scrollY + r.top + fraksi * r.height - garis());
  }

  function bacaLokal() { try { return JSON.parse(localStorage.getItem(KUNCI) || "null"); } catch { return null; } }
  function tulisLokal(isi) { try { localStorage.setItem(KUNCI, JSON.stringify(isi)); } catch { /* mode privat */ } }

  const statusTeks = $("#status-simpan-teks"), masukLagi = $("#masuk-lagi");
  function status(teks) { if (statusTeks) statusTeks.textContent = teks; }

  async function kirimPosisi(pos, keepalive) {
    const badan = { series_id: Number(series), chapter_id: pos.chapter ?? chapter, indeks: pos.indeks, fraksi: Number(pos.fraksi.toFixed(4)), rev };
    tulisLokal({ ...badan, menunggu: true, t: Date.now() });
    sedangKirim = true;
    try {
      const r = await fetch("/api/progres", { method: "POST", credentials: "same-origin", keepalive,
        headers: { "content-type": "application/json" }, body: JSON.stringify(badan) });
      if (r.status === 200) {
        rev = (await r.json()).rev;
        tulisLokal({ ...badan, rev, menunggu: false, t: Date.now() });
        berubah = false;
        masukLagi.hidden = true;
        status("Posisi tersimpan");
      } else if (r.status === 409) {
        const lain = (await r.json()).posisi;
        rev = lain.rev;
        if (bergerak) { await kirimPosisi(posisiSekarang(), keepalive); }   // pengguna sedang membaca di sini: tab ini menang
        else { tawarkan(lain); }
      } else if (r.status === 401) {
        masukLagi.hidden = false;
        status("Belum tersimpan");
      } else {
        status("Belum tersimpan");
      }
    } catch {
      status("Belum tersimpan, akan dicoba lagi");
    } finally {
      sedangKirim = false;
    }
  }

  function simpan(keepalive = false) {
    clearTimeout(jadwal);
    jadwal = null;
    if (!berubah || sedangKirim) return;
    terakhirKirim = Date.now();
    kirimPosisi(posisiSekarang(), keepalive);
  }

  function tawarkan(lain) {
    const t = $("#tawaran");
    t.hidden = false;
    $("#ikuti-tawaran").onclick = () => {
      t.hidden = true;
      if (lain.chapter_id === chapter) lompatKe(lain.indeks, lain.fraksi);
      else location.href = `/baca/${lain.chapter_id}`;
    };
  }

  // bilah atas/bawah: tampil di awal, sembunyi saat mulai menggulir, ketuk tengah layar untuk memunculkan
  document.body.classList.add("bilah-tampil");
  document.addEventListener("click", (e) => {
    if (e.target.closest("a, button, input, dialog, .bilah, .akhir")) return;
    const y = e.clientY / window.innerHeight;
    if (y > 1 / 3 && y < 2 / 3) document.body.classList.toggle("bilah-tampil");
  });

  const geser = $("#geser"), persen = $("#persen");
  function perbaruiBilah() {
    const p = posisiSekarang();
    if (geser) geser.value = String(p.indeks);
    const total = Math.max(1, imgs.length);
    const nilai = Math.round(100 * (p.indeks + p.fraksi) / total);
    if (persen) persen.textContent = `${nilai}%`;
    if (!prefetchDikirim && nilai >= 50) {
      prefetchDikirim = true;
      fetch(`/api/chapter/${chapter}/prefetch-berikut`, { method: "POST", credentials: "same-origin" }).catch(() => {});
    }
    cekSelesai();
  }
  if (geser) geser.addEventListener("input", () => lompatKe(Number(geser.value), 0));

  function cekSelesai() {
    if (sudahSelesai || selesaiDibatalkan || !imgs.length) return;
    const r = imgs[imgs.length - 1].getBoundingClientRect();
    if ((window.innerHeight - r.top) / r.height >= 0.95) {
      sudahSelesai = true;
      fetch(`/api/chapter/${chapter}/selesai`, { method: "POST", credentials: "same-origin" })
        .then((x) => { if (x.ok) $("#kartu-selesai").hidden = false; else sudahSelesai = false; })
        .catch(() => { sudahSelesai = false; });
    }
  }
  const batal = $("#batal-selesai");
  if (batal) batal.addEventListener("click", async () => {
    const r = await fetch(`/api/chapter/${chapter}/batal-selesai`, { method: "POST", credentials: "same-origin" });
    if (r.ok) { selesaiDibatalkan = true; sudahSelesai = false; $("#kartu-selesai").hidden = true; }
  });

  let tunda = false;
  window.addEventListener("scroll", () => {
    if (abaikanScroll) { abaikanScroll = false; perbaruiBilah(); return; }
    if (!bergerak) { bergerak = true; document.body.classList.remove("bilah-tampil"); $("#tawaran").hidden = true; }
    berubah = true;
    status("Menyimpan posisi...");
    if (!tunda) { tunda = true; requestAnimationFrame(() => { tunda = false; perbaruiBilah(); }); }
    if (!jadwal) jadwal = setTimeout(() => simpan(), Math.max(0, terakhirKirim + JEDA_SIMPAN - Date.now()));
  }, { passive: true });

  // tab lama yang dibuka lagi: tawarkan posisi yang lebih baru dari perangkat lain, jangan timpa diam-diam
  async function cekPerangkatLain() {
    try {
      const r = await fetch(`/api/progres/${series}`, { credentials: "same-origin" });
      if (!r.ok) return;
      const lain = (await r.json()).posisi;
      if (lain && lain.rev > rev) {
        rev = lain.rev;
        bergerak = false;
        berubah = false;
        tawarkan(lain);
      }
    } catch { /* coba lagi saat tab terlihat berikutnya */ }
  }
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") simpan(true);
    else cekPerangkatLain();
  });
  window.addEventListener("pagehide", () => simpan(true));

  // lembar pengaturan dan daftar chapter
  const pengaturan = $("#pengaturan"), daftar = $("#daftar");
  $("#buka-pengaturan").addEventListener("click", () => pengaturan.showModal());
  ["#buka-daftar", "#buka-daftar-2", "#buka-daftar-3"].forEach((s) => { const b = $(s); if (b) b.addEventListener("click", () => daftar.showModal()); });
  document.querySelectorAll(".tutup-lembar").forEach((b) => b.addEventListener("click", () => b.closest("dialog").close()));
  document.querySelectorAll("dialog.lembar").forEach((d) => d.addEventListener("click", (e) => { if (e.target === d) d.close(); }));
  document.querySelectorAll("[data-latar]").forEach((b) => b.addEventListener("click", async () => {
    const latar = b.dataset.latar;
    const r = await fetch("/api/akun/latar", { method: "POST", credentials: "same-origin",
      headers: { "content-type": "application/json" }, body: JSON.stringify({ latar }) });
    if (!r.ok) return;
    document.body.classList.remove("latar-gelap", "latar-kertas");
    document.body.classList.add(`latar-${latar}`);
    document.querySelectorAll("[data-latar]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    document.querySelector('meta[name="theme-color"]').content = latar === "gelap" ? "#2A211D" : "#FBF6EE";
  }));

  // pulihkan posisi: dari server untuk chapter ini, atau salinan lokal yang belum sempat terkirim
  const lokal = bacaLokal();
  if (lokal && lokal.menunggu && lokal.chapter_id === chapter && lokal.rev === rev) {
    lompatKe(lokal.indeks, lokal.fraksi);
    berubah = true;
    kirimPosisi({ indeks: lokal.indeks, fraksi: lokal.fraksi }, false);
  } else if (R.dataset.indeks !== "") {
    lompatKe(Number(R.dataset.indeks), Number(R.dataset.fraksi));
  } else if (imgs.length) {
    berubah = true;   // chapter baru dibuka: catat sebagai posisi terakhir
    simpan();
  }
  perbaruiBilah();
})();
