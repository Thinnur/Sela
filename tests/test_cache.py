import asyncio
import os

import pytest

from sela.cache import CacheChapter, CachePenuh
from sela.drive import DriveError, DriveLokal


class DriveLambat(DriveLokal):
    async def unduh(self, file_id, tujuan):
        await asyncio.sleep(0.05)
        await super().unduh(file_id, tujuan)


class Jam:
    t = 0.0

    def __call__(self):
        return self.t


def siapkan(tmp_path, n=3, ukuran=100, kelas=DriveLokal):
    d = kelas(tmp_path / "drive")
    ids = []
    for i in range(n):
        src = tmp_path / f"src{i}"
        src.write_bytes(bytes([i]) * ukuran)
        ids.append(asyncio.run(d.unggah(src, f"c{i}", "x", {})).id)
    return d, ids


def test_single_flight(tmp_path):
    d, (f,) = siapkan(tmp_path, 1, kelas=DriveLambat)
    c = CacheChapter(tmp_path / "cache", 10_000, d)

    async def jalan():
        return await asyncio.gather(c.path(1, f), c.path(1, f))

    a, b = asyncio.run(jalan())
    assert a == b and a.read_bytes() == bytes([0]) * 100 and d.jumlah_unduh == 1


def test_lru_buang_yang_lama(tmp_path):
    d, ids = siapkan(tmp_path)
    jam = Jam()
    c = CacheChapter(tmp_path / "cache", 250, d, jam=jam)
    asyncio.run(c.path(1, ids[0]))
    jam.t = 10.0
    asyncio.run(c.path(2, ids[1]))
    jam.t = 4000.0
    asyncio.run(c.path(3, ids[2]))
    assert sorted(p.name for p in (tmp_path / "cache").iterdir()) == ["2.cbz", "3.cbz"]
    assert c.ukuran() == 200


def test_semua_masih_dibaca_cache_penuh(tmp_path):
    d, ids = siapkan(tmp_path)
    jam = Jam()
    c = CacheChapter(tmp_path / "cache", 150, d, jam=jam)
    asyncio.run(c.path(1, ids[0]))
    jam.t = 100.0
    with pytest.raises(CachePenuh):
        asyncio.run(c.path(2, ids[1]))
    assert sorted(os.listdir(tmp_path / "cache")) == ["1.cbz"]


def test_baca_saat_drive_mati(tmp_path):
    d, (f,) = siapkan(tmp_path, 1)
    c = CacheChapter(tmp_path / "cache", 10_000, d)
    asyncio.run(c.path(1, f))
    d.gagal_unduh = DriveError("auth", "dicabut")
    assert asyncio.run(c.path(1, f)).exists()


def test_unduh_gagal_tidak_meninggalkan_part(tmp_path):
    d, (f,) = siapkan(tmp_path, 1)
    d.gagal_unduh = DriveError("sementara", "x")
    c = CacheChapter(tmp_path / "cache", 10_000, d)
    with pytest.raises(DriveError):
        asyncio.run(c.path(1, f))
    assert os.listdir(tmp_path / "cache") == []


def test_prefetch_menelan_error(tmp_path):
    d, (f,) = siapkan(tmp_path, 1)
    c = CacheChapter(tmp_path / "cache", 10_000, d)

    async def jalan():
        c.prefetch(1, f)
        c.prefetch(2, "tidak-ada")
        await asyncio.sleep(0.05)

    asyncio.run(jalan())
    assert (tmp_path / "cache" / "1.cbz").exists()
