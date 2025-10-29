import asyncio
from typing import Optional

import aiohttp
import httpx
from proxy_manager.connectors_fabric import SessionFactory
from proxy_manager.types import ProxySession


class ProxyChecker:
    @classmethod
    async def check_session(cls, proxy: ProxySession) -> Optional[ProxySession]:
        if isinstance(proxy.session, httpx.AsyncClient):
            return await cls.check_httpx_session(proxy)
        elif isinstance(proxy.session, aiohttp.ClientSession):
            return await cls.check_aiohttp_session(proxy)
        else:
            raise ValueError(f"Unsupported session type: {type(proxy.session)}")

    @classmethod
    async def check_aiohttp_session(cls, proxy: ProxySession) -> ProxySession | None:
        session = SessionFactory.create_aiohttp_session(proxy.proxy_data)
        try:
            async with asyncio.timeout(15):
                await session.get(url="https://example.com/", timeout=10.0)
                proxy.session = session
                return proxy
        except:
            await SessionFactory.close_aiohttp_session(session)
            return None

    @classmethod
    async def check_httpx_session(cls, proxy: ProxySession) -> ProxySession | None:
        session = SessionFactory.create_httpx_session(proxy.proxy_data)
        try:
            async with asyncio.timeout(15):
                await session.get(url="https://example.com/", timeout=10.0)
                proxy.session = session
                return proxy
        except:
            await SessionFactory.close_httpx_session(session)
            return None
