import asyncio

import httpx
import pytest

from sela.fetch import PengambilAman, SumberError

PUBLIK = lambda host: ["93.184.216.34"]  # noqa: E731


def pengambil(handler, resolver=PUBLIK, **kw):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return PengambilAman(client, resolver=resolver, **kw)


def ok(request):
    return httpx.Response(200, text="halo")


def jenis_error(coro):
    with pytest.raises(SumberError) as e:
        asyncio.run(coro)
    return e.value.jenis


@pytest.mark.parametrize("url", ["http://komiku.org/x", "https://evil.example/x"])
def test_tolak_skema_atau_host(url):
    assert jenis_error(pengambil(ok).ambil(url)) == "tidak_didukung"


def test_tolak_ip_privat():
    assert jenis_error(pengambil(ok, resolver=lambda h: ["10.0.0.5"]).ambil("https://komiku.org/x")) == "tidak_didukung"


def test_redirect_ke_host_privat_ditolak():
    def handler(request):
        if request.url.host == "komiku.org":
            return httpx.Response(302, headers={"location": "https://img.komiku.org/a"})
        return httpx.Response(200, text="rahasia")

    resolver = lambda h: ["127.0.0.1"] if h == "img.komiku.org" else ["93.184.216.34"]  # noqa: E731
    assert jenis_error(pengambil(handler, resolver=resolver).ambil("https://komiku.org/x")) == "tidak_didukung"


def test_redirect_ke_host_asing_ditolak():
    def handler(request):
        return httpx.Response(302, headers={"location": "https://evil.example/a"})

    assert jenis_error(pengambil(handler).ambil("https://komiku.org/x")) == "tidak_didukung"


def test_redirect_sah_diikuti():
    def handler(request):
        if request.url.path == "/x":
            return httpx.Response(301, headers={"location": "/y"})
        return httpx.Response(200, text="sampai")

    assert asyncio.run(pengambil(handler).ambil("https://komiku.org/x")).text == "sampai"


@pytest.mark.parametrize("status,header,jenis", [
    (403, {}, "ditolak"),
    (503, {"cf-mitigated": "challenge"}, "ditolak"),
    (404, {}, "tidak_ada"),
    (429, {"retry-after": "120"}, "dibatasi"),
    (502, {}, "sementara"),
])
def test_status_ke_jenis(status, header, jenis):
    p = pengambil(lambda r: httpx.Response(status, headers=header, text="x"))
    with pytest.raises(SumberError) as e:
        asyncio.run(p.ambil("https://komiku.org/x"))
    assert e.value.jenis == jenis
    if status == 429:
        assert e.value.retry_after == 120


def test_timeout_sementara():
    def handler(request):
        raise httpx.ReadTimeout("lambat", request=request)

    assert jenis_error(pengambil(handler).ambil("https://komiku.org/x")) == "sementara"


def test_batas_ukuran():
    p = pengambil(lambda r: httpx.Response(200, content=b"x" * 20_000_001))
    assert jenis_error(p.ambil("https://img.komiku.org/a.jpg")) == "berubah"


def test_host_dinamis():
    p = pengambil(ok)
    with pytest.raises(SumberError):
        p.situs_dari("https://cdn.lol/a.jpg")
    p.izinkan_host("cdn.lol", "komikindo")
    assert p.situs_dari("https://cdn.lol/a.jpg") == "komikindo"


def test_referer_dikirim():
    terlihat = {}

    def handler(request):
        terlihat["referer"] = request.headers.get("referer")
        return httpx.Response(200)

    asyncio.run(pengambil(handler).ambil("https://img.komiku.org/a.jpg", referer="https://komiku.org/ch-1/"))
    assert terlihat["referer"] == "https://komiku.org/ch-1/"


def test_semafor_per_situs():
    aktif = {"n": 0, "puncak": 0}

    async def handler(request):
        aktif["n"] += 1
        aktif["puncak"] = max(aktif["puncak"], aktif["n"])
        await asyncio.sleep(0.01)
        aktif["n"] -= 1
        return httpx.Response(200)

    p = pengambil(handler)

    async def semua():
        await asyncio.gather(*(p.ambil(f"https://img.komiku.org/{i}.jpg") for i in range(20)))

    asyncio.run(semua())
    assert aktif["puncak"] == 8


def test_timeout_ditandai_lambat():
    def handler(request):
        raise httpx.ReadTimeout("lambat", request=request)

    with pytest.raises(SumberError) as e:
        asyncio.run(pengambil(handler).ambil("https://komiku.org/x"))
    assert e.value.lambat is True


def test_jeda_antar_request_per_situs():
    waktu = []

    def handler(request):
        waktu.append(asyncio.get_event_loop().time())
        return httpx.Response(200)

    p = pengambil(handler, per_situs=1, jeda=0.1)

    async def semua():
        await asyncio.gather(*(p.ambil(f"https://img.komiku.org/{i}.jpg") for i in range(3)))

    asyncio.run(semua())
    assert all(b - a >= 0.09 for a, b in zip(waktu, waktu[1:]))
