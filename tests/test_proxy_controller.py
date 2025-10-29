# test_proxy_system.py
import pytest
import asyncio
import time
from unittest.mock import AsyncMock, patch
from proxy_manager.proxy_storage import ProxyStorage, ProxyData
from proxy_manager.types import ProxySession, RequestProxy
from proxy_manager.queues.queue_without_conditions import ProxyQueueWithoutConditions
from proxy_manager.proxy_controller import ProxyController, HttpClientType, ProxyError


class TestProxyStorage:
    def test_add_proxy_str_valid(self):
        storage = ProxyStorage()
        proxy_str = "192.168.1.1:8080:user:pass"

        proxy_data = storage.add_proxy_str(proxy_str)

        assert proxy_data.ip == "192.168.1.1"
        assert proxy_data.port == 8080
        assert proxy_data.username == "user"
        assert proxy_data.password == "pass"
        assert proxy_data in storage.proxy_dict

    def test_add_proxy_str_invalid_format(self):
        storage = ProxyStorage()
        proxy_str = "invalid_proxy_string"

        with pytest.raises(ValueError):
            storage.add_proxy_str(proxy_str)

    def test_add_proxy_str_with_conditions(self):
        storage = ProxyStorage()
        proxy_str = "192.168.1.1:8080:user:pass"
        conditions = {"country": "US", "provider": "aws"}

        proxy_data = storage.add_proxy_str(proxy_str, conditions)

        assert proxy_data.other_conditions == conditions
        assert storage.proxy_dict[proxy_data]["error_sequence"] == 0

    def test_get_proxy_by_str(self):
        storage = ProxyStorage()
        proxy_str = "192.168.1.1:8080:user:pass"
        proxy_data = storage.add_proxy_str(proxy_str)

        found_proxy = storage.get_proxy_by_str(proxy_str)

        assert found_proxy == proxy_data

    def test_report_status_initialization(self):
        storage = ProxyStorage()
        proxy_data = storage.add_proxy_str("192.168.1.1:8080:user:pass")

        # Первый вызов должен инициализировать счетчики
        storage.report_status(proxy_data, True, "new_task")

        proxy_info = storage.proxy_dict[proxy_data]
        assert "new_task_success_request" in proxy_info
        assert "new_task_error_request" in proxy_info
        assert proxy_info["new_task_success_request"] == 0
        assert proxy_info["new_task_error_request"] == 0

    def test_report_status_counters(self):
        storage = ProxyStorage()
        proxy_data = storage.add_proxy_str("192.168.1.1:8080:user:pass")

        # Несколько успешных запросов
        for _ in range(3):
            storage.report_status(proxy_data, True, "test_task")

        # Несколько ошибок
        for _ in range(2):
            storage.report_status(proxy_data, False, "test_task")

        proxy_info = storage.proxy_dict[proxy_data]
        assert proxy_info["test_task_success_request"] == 2
        assert proxy_info["test_task_error_request"] == 2
        assert proxy_info["error_sequence"] == 2

    def test_report_status_error(self):
        storage = ProxyStorage()
        proxy_data = storage.add_proxy_str("192.168.1.1:8080:user:pass")

        storage.report_status(proxy_data, False, "test_task")
        storage.report_status(proxy_data, False, "test_task")

        assert storage.proxy_dict[proxy_data]["test_task_error_request"] == 1
        assert storage.proxy_dict[proxy_data]["error_sequence"] == 2

    def test_proxy_is_valid(self):
        storage = ProxyStorage()
        proxy_data = storage.add_proxy_str("192.168.1.1:8080:user:pass")

        assert storage.proxy_is_valid(proxy_data) == True

        # Симулируем много ошибок
        storage.proxy_dict[proxy_data]["error_sequence"] = 100

        assert storage.proxy_is_valid(proxy_data) == False


class TestProxySession:
    def test_check_time_no_usage(self):
        proxy_data = ProxyData("192.168.1.1", 8080, "user", "pass")
        session = ProxySession(proxy_data, None)

        assert session.check_time("new_task", 10.0) == True

    def test_check_time_recent_usage(self):
        proxy_data = ProxyData("192.168.1.1", 8080, "user", "pass")
        session = ProxySession(proxy_data, None)
        session.update_used_time("test_task")

        assert session.check_time("test_task", 10.0) == False

    def test_check_time_old_usage(self):
        proxy_data = ProxyData("192.168.1.1", 8080, "user", "pass")
        session = ProxySession(proxy_data, None)
        session.used_time["test_task"] = time.time() - 20.0  # 20 секунд назад

        assert session.check_time("test_task", 10.0) == True

    def test_check_other_conditions_match(self):
        proxy_data = ProxyData(
            "192.168.1.1", 8080, "user", "pass", {"country": "US", "provider": "aws"}
        )
        session = ProxySession(proxy_data, None)

        conditions = {"country": "US"}
        assert session.check_other(conditions) == True

    def test_check_other_conditions_no_match(self):
        proxy_data = ProxyData("192.168.1.1", 8080, "user", "pass", {"country": "US"})
        session = ProxySession(proxy_data, None)

        conditions = {"country": "RU"}
        assert session.check_other(conditions) == False


class TestRequestProxy:
    def test_match_proxy_success(self):
        proxy_data = ProxyData("192.168.1.1", 8080, "user", "pass")
        mock_session = AsyncMock()
        proxy_session = ProxySession(proxy_data, mock_session)

        future = asyncio.Future()
        request = RequestProxy(future, "test_task", 10.0, {"country": "US"})

        # Мокаем проверки
        with patch.object(proxy_session, "check_time", return_value=True):
            with patch.object(proxy_session, "check_other", return_value=True):
                assert request.match_proxy(proxy_session) == True

    def test_match_proxy_fail_time(self):
        proxy_data = ProxyData("192.168.1.1", 8080, "user", "pass")
        mock_session = AsyncMock()
        proxy_session = ProxySession(proxy_data, mock_session)

        future = asyncio.Future()
        request = RequestProxy(future, "test_task", 10.0, {})

        with patch.object(proxy_session, "check_time", return_value=False):
            assert request.match_proxy(proxy_session) == False

    def test_match_proxy_fail_conditions(self):
        proxy_data = ProxyData("192.168.1.1", 8080, "user", "pass")
        mock_session = AsyncMock()
        proxy_session = ProxySession(proxy_data, mock_session)

        future = asyncio.Future()
        request = RequestProxy(future, "test_task", 10.0, {"country": "US"})

        with patch.object(proxy_session, "check_time", return_value=True):
            with patch.object(proxy_session, "check_other", return_value=False):
                assert request.match_proxy(proxy_session) == False


class TestProxyQueueWithoutConditions:
    @pytest.mark.asyncio
    async def test_add_and_get(self):
        queue = ProxyQueueWithoutConditions()
        proxy_data = ProxyData("192.168.1.1", 8080, "user", "pass")
        mock_session = AsyncMock()
        proxy_session = ProxySession(proxy_data, mock_session)

        await queue.add(proxy_session)
        result = await queue.get()

        assert result == proxy_session

    @pytest.mark.asyncio
    async def test_timeout(self):
        queue = ProxyQueueWithoutConditions()

        with pytest.raises(TimeoutError):
            await queue.get(timeout=0.1)

    @pytest.mark.asyncio
    async def test_release(self):
        queue = ProxyQueueWithoutConditions()
        proxy_data = ProxyData("192.168.1.1", 8080, "user", "pass")
        mock_session = AsyncMock()
        proxy_session = ProxySession(proxy_data, mock_session)

        await queue.add(proxy_session)
        retrieved = await queue.get()
        await queue.release(retrieved)

        # Должен быть снова доступен
        result = await queue.get(timeout=0.1)
        assert result == proxy_session


class TestProxyPool:
    @pytest.mark.asyncio
    async def test_add_and_immediate_get(self):
        pool = ProxyPool()
        await pool.start()

        proxy_data = ProxyData("192.168.1.1", 8080, "user", "pass")
        mock_session = AsyncMock()
        proxy_session = ProxySession(proxy_data, mock_session)

        await pool.add(proxy_session)
        result = await pool.get(timeout=1.0)

        assert result == proxy_session
        await pool.stop()

    @pytest.mark.asyncio
    async def test_get_with_conditions(self):
        pool = ProxyPool()
        await pool.start()

        proxy_data = ProxyData("192.168.1.1", 8080, "user", "pass", {"country": "US"})
        mock_session = AsyncMock()
        proxy_session = ProxySession(proxy_data, mock_session)

        await pool.add(proxy_session)

        # Подходящие условия
        result = await pool.get(other_conditions={"country": "US"}, timeout=1.0)
        assert result == proxy_session

        await pool.stop()

    @pytest.mark.asyncio
    async def test_get_no_matching_conditions(self):
        pool = ProxyPool()
        await pool.start()

        proxy_data = ProxyData("192.168.1.1", 8080, "user", "pass", {"country": "US"})
        mock_session = AsyncMock()
        proxy_session = ProxySession(proxy_data, mock_session)

        await pool.add(proxy_session)

        # Неподходящие условия - таймаут
        with pytest.raises(asyncio.TimeoutError):
            await pool.get(other_conditions={"country": "RU"}, timeout=0.5)

        await pool.stop()

    @pytest.mark.asyncio
    async def test_background_matching(self):
        pool = ProxyPool()
        await pool.start()

        proxy_data = ProxyData("192.168.1.1", 8080, "user", "pass")
        mock_session = AsyncMock()
        proxy_session = ProxySession(proxy_data, mock_session)

        # Сначала добавляем прокси
        await pool.add(proxy_session)

        # Потом запрашиваем - должен найти через фоновую задачу
        result = await pool.get(timeout=1.0)
        assert result == proxy_session

        await pool.stop()

    @pytest.mark.asyncio
    async def test_release_updates_time(self):
        pool = ProxyPool()
        await pool.start()

        proxy_data = ProxyData("192.168.1.1", 8080, "user", "pass")
        mock_session = AsyncMock()
        proxy_session = ProxySession(proxy_data, mock_session)

        await pool.add(proxy_session)
        proxy = await pool.get(timeout=1.0)

        initial_time = time.time()
        await pool.release(proxy, "test_task")

        # Проверяем что время обновилось
        assert proxy.used_time["test_task"] >= initial_time

        await pool.stop()


class TestProxyController:
    @pytest.mark.asyncio
    async def test_create_with_conditions(self):
        controller = await ProxyController.create_with_conditions(
            HttpClientType.httpx, with_check=False
        )

        assert isinstance(controller.queue, ProxyPool)
        assert controller.http_client == HttpClientType.httpx

    @pytest.mark.asyncio
    async def test_create_without_conditions(self):
        controller = await ProxyController.create_without_conditions(
            HttpClientType.aiohttp, with_check=False
        )

        assert isinstance(controller.queue, ProxyQueueWithoutConditions)
        assert controller.http_client == HttpClientType.aiohttp

    @pytest.mark.asyncio
    async def test_add_and_acquire_proxy(self):
        controller = await ProxyController.create_with_conditions(
            HttpClientType.httpx, with_check=False
        )

        await controller.add_proxy("192.168.1.1:8080:user:pass")

        async with controller.acquire(timeout=1.0) as proxy:
            assert proxy.proxy_data.ip == "192.168.1.1"
            assert proxy.proxy_data.port == 8080

    @pytest.mark.asyncio
    async def test_acquire_timeout(self):
        controller = await ProxyController.create_with_conditions(
            HttpClientType.httpx, with_check=False
        )

        with pytest.raises(asyncio.TimeoutError):
            async with controller.acquire(timeout=0.1) as proxy:
                pass

    @pytest.mark.asyncio
    async def test_proxy_error_handling(self):
        controller = await ProxyController.create_with_conditions(
            HttpClientType.httpx, with_check=False
        )

        await controller.add_proxy("192.168.1.1:8080:user:pass")

        # Получаем прокси
        async with controller.acquire(timeout=1.0) as proxy:
            # Мокаем метод сессии чтобы вызвать ошибку
            with patch.object(
                proxy.session, "get", AsyncMock(side_effect=Exception("Proxy error"))
            ):

                with pytest.raises(ProxyError):
                    await proxy.session.get("https://example.com")

    @pytest.mark.asyncio
    async def test_manually_check_proxy(self):
        controller = await ProxyController.create_with_conditions(
            HttpClientType.httpx, with_check=False
        )

        await controller.add_proxy("192.168.1.1:8080:user:pass")

        # Сначала получаем прокси чтобы потом отправить на проверку
        async with controller.acquire(timeout=1.0) as proxy:
            proxy_session = proxy

        # Добавляем прокси в список для проверки
        controller.send_proxy_to_check(proxy_session)

        # Мокаем проверку прокси
        with patch("core.proxy_check.ProxyChecker.check_session") as mock_check:
            mock_check.return_value = proxy_session  # Возвращаем валидную сессию

            await controller.manually_check_proxy("192.168.1.1:8080:user:pass")

            # Проверяем что прокси был убран из списка проверки
            assert proxy_session not in controller.proxy_check_stats

    @pytest.mark.asyncio
    async def test_multiple_concurrent_requests(self):
        controller = await ProxyController.create_with_conditions(
            HttpClientType.httpx, with_check=False
        )

        # Добавляем несколько прокси
        for i in range(3):
            await controller.add_proxy(f"192.168.1.{i+1}:8080:user:pass")

        acquired_proxies = []
        exceptions = []

        async def use_proxy(task_id):
            try:
                async with controller.acquire(
                    task_key=f"task_{task_id}", timeout=1.0
                ) as proxy:
                    await asyncio.sleep(0.01)  # Короткая пауза
                    acquired_proxies.append(proxy.proxy_data.ip)
                    return proxy.proxy_data.ip
            except (asyncio.TimeoutError, ProxyError) as e:
                exceptions.append(e)
                return None

        # Запускаем больше задач чем прокси
        tasks = [use_proxy(1) for i in range(5)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Должны успешно выполниться ровно 3 задачи (по количеству прокси)
        successful_results = [
            r for r in results if r is not None and not isinstance(r, Exception)
        ]
        assert len(successful_results) == 3
        assert len(exceptions) == 2  # 2 задачи должны получить таймаут


class TestIntegration:
    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """Интеграционный тест полного workflow"""

        # 1. Создаем контроллер с условиями
        controller = await ProxyController.create_with_conditions(
            HttpClientType.httpx, with_check=False
        )

        # 2. Добавляем прокси с разными условиями
        await controller.add_proxy(
            "192.168.1.1:8080:user:pass", {"country": "US", "provider": "aws"}
        )
        await controller.add_proxy(
            "192.168.1.2:8080:user:pass", {"country": "EU", "provider": "digitalocean"}
        )

        # 3. Запрашиваем прокси с определенными условиями
        async with controller.acquire(
            task_key="us_task", other_conditions={"country": "US"}, timeout=1.0
        ) as proxy:
            assert proxy.proxy_data.ip == "192.168.1.1"
            assert proxy.proxy_data.other_conditions["country"] == "US"

        # 4. Проверяем статистику
        storage = ProxyController.proxy_storage
        proxy_data = storage.get_proxy_by_str("192.168.1.1:8080:user:pass")
        assert storage.get_proxy_error_count(proxy_data) == 0

        # 5. Симулируем ошибку прокси
        with patch(
            "core.connectors_fabric.SessionFactory.create_httpx_session"
        ) as mock:
            mock_session = AsyncMock()
            mock_session.get = AsyncMock(side_effect=Exception("Connection failed"))
            mock.return_value = mock_session

            try:
                async with controller.acquire(
                    task_key="eu_task", other_conditions={"country": "EU"}, timeout=1.0
                ) as proxy:
                    await proxy.session.get("https://example.com")
            except ProxyError:
                pass  # Ожидаемая ошибка

        # 6. Проверяем что ошибка записана в статистику
        eu_proxy_data = storage.get_proxy_by_str("192.168.1.2:8080:user:pass")
        assert storage.get_proxy_error_count(eu_proxy_data) == 1


# Запуск тестов
if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
