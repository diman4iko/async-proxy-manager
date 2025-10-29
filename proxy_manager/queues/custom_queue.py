import asyncio
from typing import Dict, List, Optional
import logging

from proxy_manager.queues.abstract_queue import AbstractQueue
from proxy_manager.types import RequestProxy, ProxySession

logger = logging.getLogger(__name__)


class ProxyPool(AbstractQueue):
    def __init__(self):
        self.requests: List[RequestProxy] = []
        self.proxies: List[ProxySession] = []
        self.lock = asyncio.Lock()
        self._background_task: Optional[asyncio.Task] = None

    async def start(self):
        self._background_task = asyncio.create_task(self._background())

    async def stop(self):
        if self._background_task:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass

    async def _background(self):
        while True:
            try:
                await asyncio.sleep(0.5)  # Еще более частая проверка
                await self.compare_available_proxy_and_request()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Background task error: {e}")
                await asyncio.sleep(1)  # Пауза при ошибке

    async def add(self, proxy_item: ProxySession):
        async with self.lock:  # Только добавление под блокировкой
            self.proxies.append(proxy_item)

    def _check_already_existed_proxy(
            self, task_key: str, last_used: float, other_conditions: Dict[str, str]
    ) -> Optional[ProxySession]:
        for i, proxy in enumerate(self.proxies):
            if proxy.check_other(conditions=other_conditions):
                if proxy.check_time(task_key=task_key, condition=last_used):
                    return self.proxies.pop(i)
        return None

    async def get(
            self,
            task_key: str = "default",
            last_used: float = 1.0,
            other_conditions: Optional[Dict[str, str]] | None = None,
            timeout: float | None = None,
    ):
        # Проверка под блокировкой
        async with self.lock:
            for i, proxy in enumerate(self.proxies):
                if proxy.check_other(other_conditions):
                    if proxy.check_time(task_key, last_used):
                        return self.proxies.pop(i)

        # Создание запроса под блокировкой
        future = asyncio.Future()
        request = RequestProxy(
            future=future,
            task_key=task_key,
            time=last_used,
            other_conditions=other_conditions or {},
        )

        async with self.lock:
            self.requests.append(request)

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError) as e:
            async with self.lock:
                if request in self.requests:
                    self.requests.remove(request)

            if isinstance(e, asyncio.CancelledError):
                # Можно добавить логирование для отладки
                logger.debug("Request for proxy was cancelled: %s", e)

            raise  # Пробрасываем оригинальную ошибку

    async def compare_available_proxy_and_request(self):
        async with self.lock:
            i = 0
            while i < len(self.requests):
                request = self.requests[i]

                # Удаляем завершенные запросы
                if request.future.done():
                    self.requests.pop(i)
                    continue

                # Ищем подходящий прокси
                j = 0
                found_match = False
                while j < len(self.proxies):
                    proxy = self.proxies[j]

                    if request.match_proxy(proxy):
                        try:
                            request.future.set_result(proxy)
                            self.proxies.pop(j)  # Удаляем использованный прокси
                            self.requests.pop(i)  # Удаляем обработанный запрос
                            found_match = True
                            break
                        except (asyncio.InvalidStateError, asyncio.CancelledError):
                            self.requests.pop(i)  # Удаляем невалидный запрос
                            found_match = True
                            break
                    else:
                        j += 1

                if not found_match:
                    i += 1  # Переходим к следующему запросу

    async def release(self, proxy: ProxySession, task_key: str | None):
        proxy.update_used_time(task_key)
        async with self.lock:  # Только добавление под блокировкой
            self.proxies.append(proxy)
