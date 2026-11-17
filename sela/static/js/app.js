"use strict";
(() => {
  const $ = (s, el = document) => el.querySelector(s);

  function toast(pesan) {
    const t = $("#toast");
    if (!t) return;
    t.textContent = pesan;
    t.hidden = false;
    clearTimeout(toast.jeda);
    toast.jeda = setTimeout(() => { t.hidden = true; }, 3200);
  }

  async function kirim(url, data) {
    const r = await fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: { "content-type": "application/json" }, body: JSON.stringify(data ?? {}),
    });
    if (r.status === 401) {
      location.href = "/masuk";
      throw new Error("sesi habis");
    }
    return r;
  }

  async function pesanGalat(r) {
    try { return (await r.json()).galat || "Gagal. Coba lagi."; } catch { return "Gagal. Coba lagi."; }
  }

  // tombol aksi sederhana: data-aksi="post" data-url=... [data-badan] [data-konfirmasi] [data-pesan]
  document.addEventListener("click", async (e) => {
    const b = e.target.closest('[data-aksi="post"]');
    if (!b) return;
    if (b.dataset.konfirmasi && !confirm(b.dataset.konfirmasi)) return;
    b.disabled = true;
    try {
      const r = await kirim(b.dataset.url, b.dataset.badan ? JSON.parse(b.dataset.badan) : {});
      if (!r.ok) { toast(await pesanGalat(r)); return; }
      const j = r.status === 200 ? await r.json().catch(() => ({})) : {};
      if (j.diterima === false) { toast("Baru saja dicek. Coba lagi beberapa menit lagi."); return; }
      toast(b.dataset.pesan || "Beres");
      setTimeout(() => location.reload(), 700);
    } catch (err) {
      toast("Koneksi bermasalah. Coba lagi.");
    } finally {
      b.disabled = false;
    }
  });

  // dialog tambah link: pratinjau dulu, lalu tambahkan
  const dialog = $("#tambah");
  if (dialog) {
    const form = $("#tambah-form"), url = $("#tambah-url"), galat = $("#tambah-galat");
    const pv = $("#tambah-pratinjau"), kirimBtn = $("#tambah-kirim");
    let siap = false;
    const reset = () => { siap = false; pv.hidden = true; galat.hidden = true; kirimBtn.textContent = "Lihat pratinjau"; };
    const buka = (isi) => { reset(); url.value = isi || ""; dialog.showModal(); url.focus(); };
    document.querySelectorAll(".buka-tambah").forEach((b) => b.addEventListener("click", () => buka()));
    $(".tutup-dialog", dialog).addEventListener("click", () => dialog.close());
    url.addEventListener("input", reset);
    const tempel = $("#panel-tempel");
    if (tempel) tempel.addEventListener("submit", (e) => { e.preventDefault(); buka(tempel.url.value.trim()); });

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const nilai = url.value.trim();
      if (!/^https:\/\/\S+$/.test(nilai)) {
        galat.textContent = "Tempel link lengkap yang diawali https://";
        galat.hidden = false;
        return;
      }
      kirimBtn.disabled = true;
      kirimBtn.textContent = siap ? "Menambahkan..." : "Memeriksa...";
      try {
        if (!siap) {
          const r = await kirim("/api/tambah/pratinjau", { url: nilai });
          if (!r.ok) { galat.textContent = await pesanGalat(r); galat.hidden = false; kirimBtn.textContent = "Lihat pratinjau"; return; }
          const j = await r.json();
          if (j.series_id) { location.href = `/judul/${j.series_id}`; return; }
          $("#pv-judul").textContent = j.judul;
          $("#pv-info").textContent = `${j.jumlah} chapter ditemukan di ${j.sumber}`;
          const lab = $("#pv-cadangan-label");
          lab.hidden = !j.cadangan;
          if (j.cadangan) $("#pv-cadangan-teks").textContent = `Tautkan cadangan ${j.cadangan.situs} (${j.cadangan.jumlah} chapter)`;
          pv.hidden = false;
          siap = true;
          kirimBtn.textContent = "Tambahkan";
        } else {
          const r = await kirim("/api/tambah", { url: nilai, tautkan_cadangan: $("#pv-cadangan").checked });
          if (!r.ok) { galat.textContent = await pesanGalat(r); galat.hidden = false; kirimBtn.textContent = "Tambahkan"; return; }
          location.href = `/judul/${(await r.json()).series_id}`;
        }
      } catch {
        galat.textContent = "Koneksi bermasalah. Coba lagi.";
        galat.hidden = false;
        kirimBtn.textContent = siap ? "Tambahkan" : "Lihat pratinjau";
      } finally {
        kirimBtn.disabled = false;
      }
    });
  }

  // tautkan cadangan manual dari menu detail
  document.querySelectorAll(".tautkan-cadangan").forEach((f) => f.addEventListener("submit", async (e) => {
    e.preventDefault();
    const r = await kirim(f.dataset.url, { url: f.url.value.trim() });
    if (!r.ok) { toast(await pesanGalat(r)); return; }
    toast("Cadangan ditautkan");
    setTimeout(() => location.reload(), 700);
  }));

  // latar reader per akun
  document.querySelectorAll("[data-latar]").forEach((b) => b.addEventListener("click", async () => {
    const r = await kirim("/api/akun/latar", { latar: b.dataset.latar });
    if (!r.ok) { toast(await pesanGalat(r)); return; }
    document.querySelectorAll("[data-latar]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    toast("Latar disimpan untuk akunmu");
  }));

  // panel aktivitas: segarkan tiap 10 detik selama terlihat
  const balon = $("#panel-balon");
  if (balon) {
    const segarkan = async () => {
      if (document.visibilityState !== "visible") return;
      try {
        const r = await fetch("/api/aktivitas", { credentials: "same-origin" });
        if (!r.ok) return;
        const j = await r.json();
        const baru = document.createDocumentFragment();
        for (const b of j.berjalan.slice(0, 2)) {
          const li = document.createElement("li");
          li.className = "balon balon-kanan";
          li.textContent = `Mengunduh ${b.label}: ${b.gambar_selesai} dari ${b.gambar_total} gambar`;
          baru.append(li);
        }
        for (const a of j.aktivitas.slice(0, 6 - Math.min(2, j.berjalan.length))) {
          const li = document.createElement("li");
          li.className = `balon ${a.user_id ? "balon-kanan" : "balon-kiri"}`;
          li.textContent = a.teks;
          baru.append(li);
        }
        if (baru.childNodes.length) balon.replaceChildren(baru);
      } catch { /* panel hanya informasi; coba lagi di putaran berikut */ }
    };
    setInterval(segarkan, 10000);
  }
})();
