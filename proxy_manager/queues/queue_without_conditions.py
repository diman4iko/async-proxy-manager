import asyncio
from typing import Dict, Optional

from proxy_manager.queues.abstract_queue import AbstractQueue
from proxy_manager.types import ProxySession


class ProxyQueueWithoutConditions(AbstractQueue):
    def __init__(self):
        self.queue = asyncio.Queue()

    async def add(self, proxy: ProxySession) -> None:
        self.queue.put_nowait(proxy)

    async def get(
            self,
            timeout: float = 5.0,
            task_key: str = None,
            last_used: float = 1.0,
            other_conditions: Optional[Dict[str, str]] = None,
    ):
        if timeout is not None:
            try:
                return await asyncio.wait_for(self.queue.get(), timeout=timeout)
            except asyncio.TimeoutError:
                raise TimeoutError(f"Timeout ({timeout}s) while waiting for proxy.")
        else:
            return await self.queue.get()

    async def release(self, proxy: ProxySession, task_key: str = None) -> None:
        await self.add(proxy)
