"""Data untuk halaman HTML. Semua fungsi menerima user_id dari sesi, bukan dari klien."""
import json
import sqlite3
import time

from sela import progres
from sela.pembaru import NAMA_SITUS
from sela.urutan import jendela_lima

STATUS_ARSIP = {
    "antre": "Antre", "mengunduh": "Mengunduh", "mengunggah": "Mengunggah", "memverifikasi": "Memverifikasi",
    "siap": "Siap", "menunggu_ulang": "Menunggu ulang", "gagal": "Gagal", "menunggu_ruang": "Menunggu ruang",
    "hanya_cadangan": "Ada di cadangan",
}
JENIS = ("manhwa", "manga", "manhua")


def waktu_relatif(ts: float | None, sekarang: float | None = None) -> str:
    if not ts:
        return "belum pernah"
    d = (sekarang or time.time()) - ts
    if d < 60:
        return "baru saja"
    if d < 3600:
        return f"{int(d // 60)} menit lalu"
    if d < 86400:
        return f"{int(d // 3600)} jam lalu"
    if d < 86400 * 30:
        return f"{int(d // 86400)} hari lalu"
    return time.strftime("%d/%m/%Y", time.localtime(ts))


def ekstra(label_normal: str) -> bool:
    return not label_normal.isdigit()


def rak(conn: sqlite3.Connection, uid: int, q: str | None = None, f: str | None = None) -> list[dict]:
    hasil = []
    for s in conn.execute(
            "select s.*, "
            "(select count(*) from chapters c where c.series_id=s.id and c.status != 'hanya_cadangan') total, "
            "(select count(*) from chapters c where c.series_id=s.id and c.status='siap') siap, "
            "(select count(*) from chapters c join chapter_reads r on r.chapter_id=c.id and r.user_id=? "
            "  where c.series_id=s.id and r.status='selesai') tamat, "
            "(select diperbarui from reading_progress rp where rp.user_id=? and rp.series_id=s.id) dibaca_pada "
            "from series s order by coalesce(dibaca_pada, 0) desc, s.ditambahkan_pada desc", (uid, uid)):
        d = dict(s)
        d["baru"] = progres.jumlah_baru(conn, uid, s["id"])
        d["sedang_dibaca"] = d["dibaca_pada"] is not None
        hasil.append(d)
    if q:
        hasil = [d for d in hasil if q.lower() in (d["judul"] + " " + d["alias"]).lower()]
    if f == "dibaca":
        hasil = [d for d in hasil if d["sedang_dibaca"]]
    elif f == "baru":
        hasil = [d for d in hasil if d["baru"]]
    elif f == "selesai":
        hasil = [d for d in hasil if d["siap"] and d["tamat"] >= d["siap"]]
    elif f in JENIS:
        hasil = [d for d in hasil if d["jenis"] == f]
    return hasil


def _persen(conn: sqlite3.Connection, chapter_id: int, indeks: int, fraksi: float) -> int:
    r = conn.execute("select jumlah_gambar from archives where chapter_id=?", (chapter_id,)).fetchone()
    if not r or not r[0]:
        return 0
    return max(0, min(100, round(100 * (indeks + fraksi) / r[0])))


def lanjut_baca(conn: sqlite3.Connection, uid: int) -> dict | None:
    r = conn.execute("select rp.*, s.judul, s.sampul, c.label from reading_progress rp join series s on s.id=rp.series_id "
                     "join chapters c on c.id=rp.chapter_id where rp.user_id=? order by rp.diperbarui desc limit 1",
                     (uid,)).fetchone()
    if r is None:
        return None
    total = conn.execute("select count(*) from chapters where series_id=? and status != 'hanya_cadangan'",
                         (r["series_id"],)).fetchone()[0]
    return {"series_id": r["series_id"], "judul": r["judul"], "sampul": r["sampul"], "chapter_id": r["chapter_id"],
            "label": r["label"], "total": total, "persen": _persen(conn, r["chapter_id"], r["indeks"], r["fraksi"])}


def chapter_pertama_siap(conn: sqlite3.Connection, series_id: int) -> dict | None:
    r = conn.execute("select id, label from chapters where series_id=? and status='siap' order by kunci_urut limit 1",
                     (series_id,)).fetchone()
    return dict(r) if r else None


def ringkasan(conn: sqlite3.Connection) -> dict:
    siap, total = conn.execute("select sum(status='siap'), sum(status != 'hanya_cadangan') from chapters").fetchone()
    return {"siap": siap or 0, "total": total or 0,
            "proses": conn.execute("select count(*) from jobs where status='berjalan'").fetchone()[0],
            "dicek": waktu_relatif(conn.execute("select max(cek_sukses_terakhir) from series_sources").fetchone()[0]),
            "drive_mb": round((conn.execute("select coalesce(sum(ukuran), 0) from archives").fetchone()[0]) / 1e6)}


def detail(conn: sqlite3.Connection, uid: int, series_id: int, f: str | None = None, urut: str = "baru") -> dict | None:
    s = conn.execute("select * from series where id=?", (series_id,)).fetchone()
    if s is None:
        return None
    kunjungan = conn.execute("select terakhir from series_visits where user_id=? and series_id=?", (uid, series_id)).fetchone()
    kunjungan = kunjungan[0] if kunjungan else 0
    posisi = progres.ambil_posisi(conn, uid, series_id)
    sumber = [dict(x) | {"situs": NAMA_SITUS[x["adapter"]], "dicek": waktu_relatif(x["cek_sukses_terakhir"])}
              for x in conn.execute("select * from series_sources where series_id=? order by peran desc", (series_id,))]
    cadangan = next((x for x in sumber if x["peran"] == "cadangan"), None)
    baris = []
    for c in conn.execute(
            "select c.*, r.status baca, "
            "exists(select 1 from chapter_sources cs join series_sources ss on ss.id=cs.sumber_id "
            "       where cs.chapter_id=c.id and ss.peran='cadangan') ada_cadangan, "
            "(select ss.adapter from archives a join series_sources ss on ss.id=a.sumber_id where a.chapter_id=c.id) dari "
            "from chapters c left join chapter_reads r on r.chapter_id=c.id and r.user_id=? where c.series_id=? "
            f"order by c.kunci_urut {'asc' if urut == 'lama' else 'desc'}", (uid, series_id)):
        d = dict(c)
        d["status_teks"] = STATUS_ARSIP[c["status"]]
        d["ekstra"] = ekstra(c["label_normal"])
        d["baru"] = c["status"] == "siap" and (c["siap_pada"] or 0) > kunjungan and c["baca"] is None
        d["sedang"] = posisi is not None and posisi.chapter_id == c["id"]
        d["persen"] = _persen(conn, c["id"], posisi.indeks, posisi.fraksi) if d["sedang"] else 0
        d["dari_cadangan"] = cadangan is not None and c["dari"] == cadangan["adapter"]
        d["persen_unduh"] = 0
        if c["status"] == "mengunduh":
            j = conn.execute("select checkpoint from jobs where target=? and status='berjalan'", (c["id"],)).fetchone()
            cp = json.loads(j[0]) if j else {}
            if cp.get("gambar_total"):
                d["persen_unduh"] = round(100 * cp.get("gambar_selesai", 0) / cp["gambar_total"])
        baris.append(d)
    if f == "belum":
        baris = [b for b in baris if b["baca"] is None]
    elif f == "siap":
        baris = [b for b in baris if b["status"] == "siap"]
    hitung = {k: sum(1 for b in baris if b["status"] in v) for k, v in
              {"siap": ("siap",), "proses": ("antre", "mengunduh", "mengunggah", "memverifikasi", "menunggu_ulang",
                                             "menunggu_ruang"), "gagal": ("gagal",)}.items()}
    lanjut = None
    if posisi:
        lanjut = conn.execute("select id, label from chapters where id=?", (posisi.chapter_id,)).fetchone()
    return {"s": dict(s) | {"alias": json.loads(s["alias"])}, "sumber": sumber, "cadangan": cadangan, "baris": baris,
            "hitung": hitung, "total": sum(1 for b in baris if b["status"] != "hanya_cadangan"),
            "lanjut": dict(lanjut) if lanjut else None, "pertama": chapter_pertama_siap(conn, series_id)}


def baca(conn: sqlite3.Connection, uid: int, chapter_id: int) -> dict | None:
    c = conn.execute("select * from chapters where id=?", (chapter_id,)).fetchone()
    if c is None:
        return None
    s = conn.execute("select id, judul from series where id=?", (c["series_id"],)).fetchone()
    semua = [dict(x) for x in conn.execute(
        "select c.id, c.label, c.label_normal, c.status, r.status baca from chapters c left join chapter_reads r "
        "on r.chapter_id=c.id and r.user_id=? where c.series_id=? and c.status != 'hanya_cadangan' order by c.kunci_urut",
        (uid, c["series_id"]))]
    i = next(k for k, x in enumerate(semua) if x["id"] == chapter_id)
    per_label = {x["label_normal"]: x for x in semua}
    petak = []
    for ln in jendela_lima([x["label_normal"] for x in semua], c["label_normal"]):
        x = per_label[ln]
        keadaan = "belum-siap" if x["status"] != "siap" else ("selesai" if x["baca"] == "selesai" else "belum")
        petak.append({"id": x["id"], "label": ln, "keadaan": keadaan})
    berikut = dict(semua[i + 1]) if i + 1 < len(semua) else None
    if berikut and berikut["status"] == "mengunduh":
        j = conn.execute("select checkpoint from jobs where target=? and status='berjalan'", (berikut["id"],)).fetchone()
        cp = json.loads(j[0]) if j else {}
        berikut["persen"] = round(100 * cp.get("gambar_selesai", 0) / cp["gambar_total"]) if cp.get("gambar_total") else 0
    if berikut:
        berikut["status_teks"] = STATUS_ARSIP[berikut["status"]]
    sebelum = semua[i - 1] if i > 0 and semua[i - 1]["status"] == "siap" else None
    arsip = conn.execute("select manifest from archives where chapter_id=?", (chapter_id,)).fetchone()
    posisi = progres.ambil_posisi(conn, uid, c["series_id"])
    latar = conn.execute("select latar_reader from users where id=?", (uid,)).fetchone()[0]
    return {"c": dict(c), "s": dict(s), "gambar": json.loads(arsip[0])["gambar"] if arsip else None,
            "posisi": posisi if posisi and posisi.chapter_id == chapter_id else None, "rev": posisi.rev if posisi else 0,
            "latar": latar, "sebelum": sebelum, "berikut": berikut, "petak": petak, "semua": semua,
            "selesai": semua[i]["baca"] == "selesai", "status_teks": STATUS_ARSIP[c["status"]]}


def aktivitas(conn: sqlite3.Connection, batas: int = 30) -> list[dict]:
    return [dict(x) | {"waktu": waktu_relatif(x["pada"])}
            for x in conn.execute("select * from activity order by id desc limit ?", (batas,))]
