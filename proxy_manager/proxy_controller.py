import asyncio
import logging
from contextlib import asynccontextmanager
from enum import Enum
from typing import Dict

import aiohttp
import httpx
from python_socks._errors import ProxyConnectionError as PySocksProxyConnectionError

from proxy_manager.connectors_fabric import SessionFactory
from proxy_manager.proxy_check import ProxyChecker
from proxy_manager.queues.custom_queue import ProxyPool
from proxy_manager.queues.queue_without_conditions import ProxyQueueWithoutConditions
from proxy_manager.types import ProxySession
from .proxy_storage import ProxyStorage

logger = logging.getLogger(__name__)


class ProxyError(Exception):
    pass


class HttpClientType(Enum):
    httpx = 1
    aiohttp = 2


class ProxyController:
    proxy_storage = ProxyStorage()
    proxy_clients = []  # слегка костыльный метод для принудительного закрытия всех коннекторов

    @classmethod
    async def close_all_connectors(cls):
        for client in cls.proxy_clients:
            if isinstance(client, aiohttp.ClientSession):
                await SessionFactory.close_aiohttp_session(client)

            if isinstance(client, httpx.AsyncClient):
                await SessionFactory.close_httpx_session(client)

    @classmethod
    async def create_with_conditions(cls, http_client: HttpClientType, with_check: bool = True):
        queue = ProxyPool()
        await queue.start()
        return cls(http_client, queue, with_check)

    @classmethod
    async def create_without_conditions(cls, http_client: HttpClientType, with_check: bool = True):
        queue = ProxyQueueWithoutConditions()
        return cls(http_client, queue, with_check)

    def __init__(
            self,
            http_client: HttpClientType,
            queue: ProxyPool | ProxyQueueWithoutConditions,
            with_check: bool
    ):
        self.http_client = http_client
        self.queue = queue
        self.proxy_check_stats = {}  # количество проверок, которые уже прошла прокси
        if with_check:
            self.check_proxy_task: asyncio.Task = asyncio.create_task(self.proxy_checker_task())
        self.lock = asyncio.Lock()

    async def stop_proxy_checker_task(self):
        try:
            self.check_proxy_task.cancel()
        except asyncio.CancelledError:
            pass

    async def proxy_checker_task(self):
        while True:
            await asyncio.sleep(1000)

            # Первая блокировка: составление списка для проверки
            proxies_to_check = []
            async with self.lock:
                for proxy, check_count in list(self.proxy_check_stats.items()):
                    if check_count <= 3:
                        proxies_to_check.append(proxy)
            # Проверка прокси БЕЗ блокировки (сетевые операции)
            checked_proxies = []
            for proxy in proxies_to_check:
                try:
                    new_proxy_session = await ProxyChecker.check_session(proxy)
                    checked_proxies.append((proxy, new_proxy_session))
                except Exception as e:
                    logger.debug(f"Proxy check failed for {proxy.proxy_data.ip}: {e}")
                    checked_proxies.append((proxy, None))

            # Вторая блокировка: обновление состояния
            async with self.lock:
                for proxy, new_proxy_session in checked_proxies:
                    if proxy not in self.proxy_check_stats:
                        continue  # Прокси мог быть удален параллельно

                    if new_proxy_session is not None:
                        # Успешная проверка - возвращаем в очередь
                        await self.queue.add(new_proxy_session)
                        self.proxy_check_stats.pop(proxy)
                        ProxyController.proxy_storage.update_proxy_status(proxy.proxy_data)
                    else:
                        # Неудачная проверка - увеличиваем счетчик
                        self.proxy_check_stats[proxy] += 1

    async def manually_check_proxy(self, proxy: str):
        try:
            proxy_to_check = ProxyController.proxy_storage.get_proxy_by_str(proxy)
            async with self.lock:
                for proxy in list(self.proxy_check_stats):
                    if proxy_to_check == proxy.proxy_data:
                        new_proxy_session = await ProxyChecker.check_session(proxy)
                        if new_proxy_session is not None:
                            await self.queue.add(new_proxy_session)
                            self.proxy_check_stats.pop(proxy)
                            ProxyController.proxy_storage.update_proxy_status(new_proxy_session.proxy_data)
                            return True
                        else:
                            self.proxy_check_stats[proxy] += 1
                            return False
        except ValueError:
            pass

    async def add_proxy(self, proxy: str, conditions: Dict = None):
        proxy_object = ProxyController.proxy_storage.add_proxy_str(proxy=proxy, other_conditions=conditions)
        if self.http_client == HttpClientType.httpx:
            connector = SessionFactory.create_httpx_session(proxy_object)
            ProxyController.proxy_clients.append(connector)
            session = ProxySession(proxy_data=proxy_object, session=connector)
        else:
            connector = SessionFactory.create_aiohttp_session(proxy_object)
            ProxyController.proxy_clients.append(connector)
            session = ProxySession(proxy_data=proxy_object, session=connector)

        await self.queue.add(session)

    async def close_proxy_client(self, proxy: ProxySession):
        if self.http_client == HttpClientType.httpx:
            await SessionFactory.close_httpx_session(proxy=proxy.session)
        if self.http_client == HttpClientType.aiohttp:
            await SessionFactory.close_aiohttp_session(proxy=proxy.session)

    def send_proxy_to_check(self, proxy: ProxySession):
        self.proxy_check_stats[proxy] = 0

    @asynccontextmanager
    async def acquire(
            self,
            task_key: str = "default",
            time_condition: float = 5.0,
            timeout: float | None = 100.0,
            other_conditions=None,
    ):
        """
        :param task_key: название задачи для которой нужна прокси
        :param time_condition:  требование по времени до скольких то секунд
        :param timeout: таймаут на поиск None будет искать бесконечно
        :param other_conditions: словарь с остальными требованиями
        :return:
        """
        if other_conditions is None:
            other_conditions = {}
        try:
            proxy = await self.queue.get(
                task_key=task_key,
                last_used=time_condition,
                timeout=timeout,
                other_conditions=other_conditions,
            )
        except asyncio.TimeoutError:
            raise
        try:
            async with asyncio.timeout(20):
                yield proxy
            await self.queue.release(proxy=proxy, task_key=task_key)
            ProxyController.proxy_storage.report_status(proxy=proxy.proxy_data, task_key=task_key, request_status=True)
        except (
                httpx.ProxyError,
                httpx.ConnectError,
                httpx.ReadTimeout,
                httpx.RemoteProtocolError,
                httpx.ProtocolError,
                asyncio.TimeoutError,
                aiohttp.ClientProxyConnectionError,
                aiohttp.ServerTimeoutError,
                aiohttp.ClientResponseError,
                aiohttp.ClientConnectionError,
                aiohttp.ClientOSError,
                asyncio.TimeoutError,
                PySocksProxyConnectionError,
        ) as e:
            ProxyController.proxy_storage.report_status(proxy=proxy.proxy_data, request_status=False, task_key=task_key)
            if not ProxyController.proxy_storage.proxy_is_valid(proxy.proxy_data):
                await self.close_proxy_client(proxy)
                self.send_proxy_to_check(proxy)
            else:
                await self.queue.release(proxy=proxy, task_key=task_key)
            logger.debug("request if failed: ", e)
            raise ProxyError("Proxy is bad")
        except Exception:
            raise
