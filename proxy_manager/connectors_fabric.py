import aiohttp
import httpx
from aiohttp_socks import ProxyType, ProxyConnector

from proxy_manager.proxy_storage import ProxyData


class SessionFactory:
    @classmethod
    def _create_aiohttp_socks_con(cls, proxy: ProxyData) -> ProxyConnector:
        return ProxyConnector(
            host=proxy.ip,
            port=proxy.port,
            username=proxy.username,
            password=proxy.password,
            proxy_type=ProxyType.SOCKS5,
        )

    @classmethod
    def create_aiohttp_session(cls, proxy: ProxyData) -> aiohttp.ClientSession:
        return aiohttp.ClientSession(connector=cls._create_aiohttp_socks_con(proxy))

    @classmethod
    def create_httpx_session(cls, proxy: ProxyData) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            proxy=f"socks5://{proxy.username}:{proxy.password}@{proxy.ip}:{str(proxy.port)}",
            http2=True,
        )

    @classmethod
    async def close_httpx_session(cls, proxy):
        await proxy.aclose()

    @classmethod
    async def close_aiohttp_session(cls, proxy):
        await proxy.close()
