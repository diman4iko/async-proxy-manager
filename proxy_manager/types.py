import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, Union, Optional

import aiohttp
import httpx


@dataclass(eq=False)
class ProxyData:
    ip: str
    port: int
    username: str
    password: str
    other_conditions: Dict[str, str] = field(default_factory=dict)

    def __hash__(self):
        return hash((self.ip, self.port))

    def __eq__(self, other):
        if isinstance(other, ProxyData):
            return other.ip == self.ip and other.port == self.port
        return False


@dataclass
class ProxySession:
    """Универсальный класс для сессии с прокси"""
    proxy_data: ProxyData
    session: Union[aiohttp.ClientSession, httpx.AsyncClient]
    used_time: Dict[str, float] = field(default_factory=dict)

    def __hash__(self):
        return hash(self.proxy_data)

    def check_time(self, task_key: str, condition: float) -> bool:
        try:
            elapsed_time = time.time() - self.used_time[task_key]
            return elapsed_time >= condition
        except KeyError:
            return True

    def check_other(self, conditions: Dict[str, str]) -> bool:
        if conditions is None:
            return True
        for key in conditions.keys():
            if conditions[key] != self.proxy_data.other_conditions.get(key):
                return False
        return True

    def update_used_time(self, task_key: Optional[str] = None):
        if task_key is None:
            task_key = "default"
        self.used_time[task_key] = time.time()


@dataclass
class RequestProxy:
    future: asyncio.Future
    task_key: str = "default"
    time: float = 1.0
    other_conditions: Dict[str, str] = field(default_factory=dict)

    def match_proxy(self, proxy: ProxySession) -> bool:
        if proxy.check_time(self.task_key, self.time):
            if proxy.check_other(self.other_conditions):
                return True
        return False
