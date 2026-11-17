import asyncio
import errno
from dataclasses import replace

import pytest

from sela import db, ingest
from sela.drive import DriveError
from sela.fetch import SumberError
from sela.worker import Worker, coba_lagi_chapter, coba_lagi_sumber


@pytest.fixture
def path_db(tmp_path):
    p = tmp_path / "w.db"
    c = db.buka(p)
    db.migrasi(c)
    c.execute("insert into series(id, judul, ditambahkan_pada) values(1, 'X', 0)")
    c.execute("insert into series_sources(id, series_id, adapter, url, peran) values(1, 1, 'komiku', 'https://komiku.org/manga/x/', 'utama')")
    c.execute("insert into series_sources(id, series_id, adapter, url, peran) values(2, 1, 'komikindo', 'https://komikindo.ch/komik/x/', 'cadangan')")
    c.close()
    return p


def buat_job(path_db, n, sumber_id=1):
    c = db.buka(path_db)
    ids = []
    for _ in range(n):
        k = c.execute("select count(*) from chapters").fetchone()[0] + 1
        cid = c.execute("insert into chapters(series_id, label, label_normal, kunci_urut) values(1, ?, ?, ?)",
                        (f"Chapter {k}", str(k), k)).lastrowid
        ids.append(ingest.buat_job_unduh(c, cid, sumber_id, 0.0))
    c.close()
    return ids


class Jam:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def worker(path_db, setelan, proses, paralel=3, sisa=10_000_000_000, jam=None):
    s = replace(setelan, chapter_paralel=paralel)
    return Worker(s, lambda: db.buka(path_db), None, None, proses=proses, jam=jam or Jam(), sisa_disk=lambda: sisa)


async def tunggu_berjalan(w):
    while w.berjalan:
        await asyncio.gather(*[t for t, _ in list(w.berjalan.values())], return_exceptions=True)


def baris(path_db, sql, *arg):
    c = db.buka(path_db)
    r = c.execute(sql, arg).fetchone()
    c.close()
    return r


@pytest.mark.parametrize("paralel", [3, 4])
def test_maksimal_paralel(path_db, setelan, paralel):
    aktif = {"n": 0, "puncak": 0}

    async def proses(buka_db, p, drive, s, job_id):
        aktif["n"] += 1
        aktif["puncak"] = max(aktif["puncak"], aktif["n"])
        await asyncio.sleep(0.03)
        aktif["n"] -= 1
        c = buka_db()
        c.execute("update jobs set status='selesai' where id=?", (job_id,))
        c.close()

    buat_job(path_db, 6)
    w = worker(path_db, setelan, proses, paralel=paralel)

    async def jalan():
        for _ in range(50):
            await w.satu_putaran()
            await asyncio.sleep(0.005)
        await tunggu_berjalan(w)

    asyncio.run(jalan())
    assert aktif["puncak"] == paralel
    assert baris(path_db, "select count(*) from jobs where status='selesai'")[0] == 6


def test_backoff_lalu_gagal(path_db, setelan):
    async def proses(*a):
        raise SumberError("sementara", "server sumber error")

    buat_job(path_db, 1)
    jam = Jam()
    w = worker(path_db, setelan, proses, jam=jam)
    jeda = []

    async def jalan():
        for _ in range(5):
            assert await w.satu_putaran() == 1
            await tunggu_berjalan(w)
            j = baris(path_db, "select status, jalan_setelah from jobs")
            if j["status"] == "antre":
                jeda.append(j["jalan_setelah"] - jam.t)
                jam.t = j["jalan_setelah"]

    asyncio.run(jalan())
    assert jeda == [60, 300, 1800, 7200]
    assert tuple(baris(path_db, "select status from jobs")) == ("gagal",)
    ch = baris(path_db, "select status, pesan_status from chapters")
    assert ch["status"] == "gagal" and "server sumber error" in ch["pesan_status"]


def test_status_menunggu_ulang_di_antara_percobaan(path_db, setelan):
    async def proses(*a):
        raise SumberError("sementara", "x")

    buat_job(path_db, 1)
    w = worker(path_db, setelan, proses)

    async def jalan():
        await w.satu_putaran()
        await tunggu_berjalan(w)

    asyncio.run(jalan())
    assert baris(path_db, "select status from chapters")[0] == "menunggu_ulang"


def test_ditolak_menjeda_sumber(path_db, setelan):
    async def proses(buka_db, p, drive, s, job_id):
        raise SumberError("ditolak", "akses ditolak (HTTP 403)")

    j1, j2 = buat_job(path_db, 2)
    w = worker(path_db, setelan, proses, paralel=1)

    async def jalan():
        assert await w.satu_putaran() == 1
        await tunggu_berjalan(w)
        assert await w.satu_putaran() == 0
        c = db.buka(path_db)
        coba_lagi_sumber(c, 1)
        c.close()
        assert await w.satu_putaran() == 1
        await tunggu_berjalan(w)

    asyncio.run(jalan())
    assert baris(path_db, "select jenis_error from series_sources where id=1")[0] == "ditolak"


def test_429_turunkan_situs(path_db, setelan):
    async def lambat(*a):
        await asyncio.sleep(0.05)

    async def dibatasi(*a):
        raise SumberError("dibatasi", "terlalu banyak", retry_after=120)

    buat_job(path_db, 1)
    w = worker(path_db, setelan, dibatasi, paralel=3)
    jam = w.jam

    async def jalan():
        await w.satu_putaran()
        await tunggu_berjalan(w)
        assert "komiku" in w.turun
        assert baris(path_db, "select jalan_setelah from jobs")[0] - jam.t == 120
        buat_job(path_db, 3, sumber_id=1)
        buat_job(path_db, 3, sumber_id=2)
        w.proses = lambat
        mulai = await w.satu_putaran()
        situs = [st for _, st in w.berjalan.values()]
        await tunggu_berjalan(w)
        return mulai, situs

    mulai, situs = asyncio.run(jalan())
    assert mulai == 3 and situs.count("komiku") == 1 and situs.count("komikindo") == 2
    w.normalkan_situs("komiku")
    assert "komiku" not in w.turun


def test_anggaran_disk_menunggu_ruang(path_db, setelan):
    async def proses(*a):
        raise AssertionError("tidak boleh jalan")

    buat_job(path_db, 1)
    w = worker(path_db, setelan, proses, sisa=2_000_000_000)
    assert asyncio.run(w.satu_putaran()) == 0
    assert baris(path_db, "select status from chapters")[0] == "menunggu_ruang"


def test_anggaran_tmp_cache_penuh(path_db, setelan):
    async def proses(*a):
        raise AssertionError("tidak boleh jalan")

    buat_job(path_db, 1)
    s = replace(setelan, anggaran_disk=1000)
    setelan.dir_cache.mkdir(parents=True)
    (setelan.dir_cache / "x.cbz").write_bytes(b"x" * 10)
    w = Worker(s, lambda: db.buka(path_db), None, None, proses=proses, jam=Jam(), sisa_disk=lambda: 10**12)
    assert asyncio.run(w.satu_putaran()) == 0


def test_pulihkan_berjalan_ke_antre(path_db, setelan):
    buat_job(path_db, 1)
    c = db.buka(path_db)
    c.execute("update jobs set status='berjalan'")
    c.execute("update chapters set status='mengunggah'")
    c.close()
    worker(path_db, setelan, None).pulihkan()
    assert tuple(baris(path_db, "select j.status, c.status from jobs j join chapters c on c.id=j.target")) == ("antre", "antre")


def test_jeda_antrean(path_db, setelan):
    buat_job(path_db, 1)
    c = db.buka(path_db)
    db.kv_set(c, "antrean_jeda", "1")
    c.close()
    assert asyncio.run(worker(path_db, setelan, None).satu_putaran()) == 0


def test_enospc_rapi(path_db, setelan):
    async def proses(buka_db, p, drive, s, job_id):
        (s.dir_tmp / str(job_id)).mkdir(parents=True)
        (s.dir_tmp / str(job_id) / "x").write_bytes(b"x")
        raise OSError(errno.ENOSPC, "No space left on device")

    (job,) = buat_job(path_db, 1)
    w = worker(path_db, setelan, proses)

    async def jalan():
        await w.satu_putaran()
        await tunggu_berjalan(w)

    asyncio.run(jalan())
    assert tuple(baris(path_db, "select j.status, c.status from jobs j join chapters c on c.id=j.target")) == ("antre", "menunggu_ruang")
    assert not (setelan.dir_tmp / str(job)).exists()


def test_token_dicabut_berhenti(path_db, setelan):
    async def proses(*a):
        raise DriveError("auth", "izin Drive dicabut")

    buat_job(path_db, 2)
    w = worker(path_db, setelan, proses, paralel=1)

    async def jalan():
        assert await w.satu_putaran() == 1
        await tunggu_berjalan(w)
        return await w.satu_putaran()

    assert asyncio.run(jalan()) == 0
    c = db.buka(path_db)
    assert db.kv_ambil(c, "drive_status") == "perlu_sambung"
    assert c.execute("select max(percobaan) from jobs").fetchone()[0] == 0
    c.close()


def test_coba_lagi_chapter(path_db, setelan):
    buat_job(path_db, 1)
    c = db.buka(path_db)
    c.execute("update jobs set status='gagal', percobaan=5")
    c.execute("update chapters set status='gagal'")
    coba_lagi_chapter(c, 1)
    assert tuple(c.execute("select j.status, j.percobaan, ch.status from jobs j join chapters ch on ch.id=j.target").fetchone()) == ("antre", 0, "antre")
    c.close()
