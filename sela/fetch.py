import asyncio
import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urljoin, urlsplit

import httpx

Jenis = Literal["tidak_didukung", "tidak_ada", "berubah", "ditolak", "dibatasi", "sementara"]

HOST_STATIS = {"komiku.org": "komiku", "img.komiku.org": "komiku", "komikindo.ch": "komikindo"}
USER_AGENT = "Mozilla/5.0 (compatible; Sela/1.0; pembaca pribadi)"
MAKS_REDIRECT = 5


class SumberError(Exception):
    def __init__(self, jenis: Jenis, pesan: str, retry_after: float | None = None):
        super().__init__(f"{jenis}: {pesan}")
        self.jenis = jenis
        self.pesan = pesan
        self.retry_after = retry_after


@dataclass(frozen=True)
class Respons:
    url: str
    headers: httpx.Headers
    content: bytes

    @property
    def text(self) -> str:
        charset = httpx.Headers(self.headers).get("content-type", "")
        enc = charset.split("charset=")[-1].strip() if "charset=" in charset else "utf-8"
        try:
            return self.content.decode(enc, errors="replace")
        except LookupError:
            return self.content.decode("utf-8", errors="replace")


def resolve_dns(host: str) -> list[str]:
    return sorted({info[4][0] for info in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)})


def _retry_after(nilai: str | None) -> float | None:
    try:
        return float(nilai) if nilai else None
    except ValueError:
        return None


class PengambilAman:
    def __init__(self, client: httpx.AsyncClient, per_situs: int = 8,
                 resolver: Callable[[str], list[str]] = resolve_dns, maks_byte: int = 20_000_000):
        self.client = client
        self.per_situs = per_situs
        self.resolver = resolver
        self.maks_byte = maks_byte
        self._host = dict(HOST_STATIS)
        self._semafor: dict[str, asyncio.Semaphore] = {}

    def izinkan_host(self, host: str, situs: str) -> None:
        self._host[host.lower()] = situs

    def situs_dari(self, url: str) -> str:
        bagian = urlsplit(url)
        if bagian.scheme != "https":
            raise SumberError("tidak_didukung", "hanya https yang diizinkan")
        situs = self._host.get((bagian.hostname or "").lower())
        if situs is None:
            raise SumberError("tidak_didukung", f"host tidak dikenal: {bagian.hostname}")
        return situs

    async def _cek_ip(self, host: str) -> None:
        # shortcut: DNS dicek sebelum koneksi (rebinding masih mungkin), naikkan ke pinning IP kalau sumber jadi tak tepercaya
        try:
            alamat = await asyncio.to_thread(self.resolver, host)
        except OSError as e:
            raise SumberError("sementara", f"DNS gagal untuk {host}") from e
        if not alamat or not all(ipaddress.ip_address(a).is_global for a in alamat):
            raise SumberError("tidak_didukung", f"{host} mengarah ke alamat privat")

    async def ambil(self, url: str, *, referer: str | None = None) -> Respons:
        situs = self.situs_dari(url)
        semafor = self._semafor.setdefault(situs, asyncio.Semaphore(self.per_situs))
        async with semafor:
            for _ in range(MAKS_REDIRECT + 1):
                self.situs_dari(url)
                await self._cek_ip(urlsplit(url).hostname or "")
                headers = {"user-agent": USER_AGENT}
                if referer:
                    headers["referer"] = referer
                try:
                    resp = await self.client.send(self.client.build_request("GET", url, headers=headers), stream=True)
                except httpx.TimeoutException as e:
                    raise SumberError("sementara", "waktu habis") from e
                except httpx.TransportError as e:
                    raise SumberError("sementara", "koneksi gagal") from e
                try:
                    if resp.is_redirect:
                        url = urljoin(url, resp.headers["location"])
                        continue
                    self._cek_status(resp)
                    return Respons(url, resp.headers, await self._baca(resp))
                finally:
                    await resp.aclose()
        raise SumberError("berubah", "terlalu banyak redirect")

    def _cek_status(self, resp: httpx.Response) -> None:
        s = resp.status_code
        if resp.headers.get("cf-mitigated") == "challenge" or s in (401, 403, 451):
            raise SumberError("ditolak", f"akses ditolak (HTTP {s})")
        if s in (404, 410):
            raise SumberError("tidak_ada", f"tidak ditemukan (HTTP {s})")
        if s == 429:
            raise SumberError("dibatasi", "terlalu banyak request", _retry_after(resp.headers.get("retry-after")))
        if s != 200:
            raise SumberError("sementara", f"HTTP {s}")

    async def _baca(self, resp: httpx.Response) -> bytes:
        isi = bytearray()
        try:
            async for potong in resp.aiter_bytes():
                isi += potong
                if len(isi) > self.maks_byte:
                    raise SumberError("berubah", "respons terlalu besar")
        except httpx.TransportError as e:
            raise SumberError("sementara", "koneksi terputus") from e
        return bytes(isi)
