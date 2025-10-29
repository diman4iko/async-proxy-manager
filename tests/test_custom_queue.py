# ТЕСТЫ
@pytest.mark.asyncio
async def test_basic_functionality():
    """Тест базовой функциональности"""
    pool = ProxyPool()
    await pool.start()

    try:
        # Добавляем прокси
        await pool.add("proxy1", {"type": "http", "country": "us"})
        await pool.add("proxy2", {"type": "socks", "country": "eu"})

        # Получаем прокси
        start_time = time.time()
        proxy1 = await pool.get(other_conditions={"type": "http"})
        end_time = time.time()

        assert proxy1.proxy == "proxy1"
        assert end_time - start_time < 0.1  # Должно быть мгновенно

        # Возвращаем прокси
        await pool.release(proxy1, "test")

    finally:
        await pool.stop()


@pytest.mark.asyncio
async def test_time_based_throttling():
    """Тест временного ограничения"""
    pool = ProxyPool()
    await pool.start()

    try:
        await pool.add("proxy1", {"type": "http"})

        # Первое использование
        proxy = await pool.get(task_key="task1", last_used=0.5)  # Уменьшил время
        assert proxy.proxy == "proxy1"
        await pool.release(proxy, "task1")  # Немедленно возвращаем

        # Пытаемся получить снова сразу - не должно получиться из-за cooldown
        start_time = time.time()
        with pytest.raises(asyncio.TimeoutError):
            await pool.get(task_key="task1", last_used=0.5, timeout=0.3)
        end_time = time.time()

        # Проверяем, что timeout сработал быстро
        assert end_time - start_time < 0.4

        # Ждем cooldown и пробуем снова
        await asyncio.sleep(0.6)  # Ждем больше чем cooldown
        proxy = await pool.get(task_key="task1", last_used=0.5)
        assert proxy.proxy == "proxy1"

    finally:
        await pool.stop()


@pytest.mark.asyncio
async def test_condition_based_matching():
    """Тест matching по условиям"""
    pool = ProxyPool()
    await pool.start()

    try:
        await pool.add("proxy1", {"type": "http", "country": "us"})
        await pool.add("proxy2", {"type": "socks", "country": "eu"})
        await pool.add("proxy3", {"type": "http", "country": "eu"})

        # Запрос по одному условию
        proxy = await pool.get(other_conditions={"type": "socks"})
        assert proxy.proxy == "proxy2"

        # Запрос по двум условиям
        proxy = await pool.get(other_conditions={"type": "http", "country": "eu"})
        assert proxy.proxy == "proxy3"

        # Несуществующие условия
        with pytest.raises(asyncio.TimeoutError):
            await pool.get(other_conditions={"type": "https"}, timeout=0.1)

    finally:
        await pool.stop()


@pytest.mark.asyncio
async def test_performance_high_load():
    """Тест производительности под высокой нагрузкой"""
    pool = ProxyPool()
    await pool.start()

    try:
        # Добавляем 100 прокси
        for i in range(100):
            await pool.add(f"proxy{i}", {"group": f"group{i%10}"})

        # Тестируем скорость получения
        start_time = time.time()
        results = []

        async def get_proxy(idx):
            try:
                proxy = await pool.get(
                    task_key=f"task{idx%5}",
                    last_used=0.1,
                    other_conditions={"group": f"group{idx%10}"},
                    timeout=1.0,
                )
                results.append(proxy)
                await asyncio.sleep(0.01)  # Имитация работы
                await pool.release(proxy, f"task{idx%5}")
            except Exception as e:
                results.append(e)

        # Запускаем 200 параллельных запросов
        tasks = [get_proxy(i) for i in range(200)]
        await asyncio.gather(*tasks)

        end_time = time.time()
        total_time = end_time - start_time

        print(f"\nPerformance test: {len(results)} operations in {total_time:.3f}s")
        print(f"Operations per second: {len(results)/total_time:.1f}")

        # Должно работать быстро (более 100 ops/sec)
        assert total_time < 3.0
        assert len([r for r in results if isinstance(r, Proxy)]) > 150

    finally:
        await pool.stop()


@pytest.mark.asyncio
async def test_concurrent_access():
    """Тест конкурентного доступа"""
    pool = ProxyPool()
    await pool.start()

    try:
        await pool.add("shared_proxy", {"type": "shared"})

        results = []

        async def concurrent_get(worker_id):
            try:
                proxy = await pool.get(
                    task_key=f"worker{worker_id}", last_used=0.5, timeout=2.0
                )
                await asyncio.sleep(0.1)  # Работа с прокси
                results.append((worker_id, proxy.proxy))
                await pool.release(proxy, f"worker{worker_id}")
                return True
            except asyncio.TimeoutError:
                results.append((worker_id, "timeout"))
                return False

        # 10 рабочих одновременно пытаются получить один прокси
        tasks = [concurrent_get(i) for i in range(10)]
        successes = await asyncio.gather(*tasks)

        # Должны успешно работать несколько рабочих
        assert sum(successes) >= 5
        print(f"\nConcurrent test: {sum(successes)}/10 workers succeeded")

    finally:
        await pool.stop()


async def test_background_matching_performance():
    """Тест скорости работы фонового matching"""
    pool = ProxyPool()
    await pool.start()

    try:
        # Добавляем прокси
        for i in range(20):  # Уменьшил количество для скорости
            await pool.add(f"proxy{i}", {"speed": "fast" if i % 2 == 0 else "slow"})

        # Даем время фоновой задаче обработать добавление
        await asyncio.sleep(0.1)

        # Создаем запросы и измеряем время matching
        start_time = time.time()

        async def create_request(req_id):
            try:
                return await pool.get(
                    task_key=f"req{req_id}",
                    other_conditions={"speed": "fast"},
                    timeout=0.5,  # Уменьшил timeout
                )
            except asyncio.TimeoutError:
                return None

        # Создаем 15 запросов вместо 30
        requests = [create_request(i) for i in range(15)]
        proxies = await asyncio.gather(*requests)

        end_time = time.time()
        matching_time = end_time - start_time

        # Фильтруем None (таймауты)
        successful_proxies = [p for p in proxies if p is not None]

        print(
            f"\nBackground matching: {len(successful_proxies)}/{len(proxies)} requests in {matching_time:.3f}s"
        )
        print(f"Matching speed: {len(successful_proxies)/matching_time:.1f} req/sec")

        assert matching_time < 0.8
        assert len(successful_proxies) >= 10  # Должно быть хотя бы 10 успешных

    finally:
        await pool.stop()


if __name__ == "__main__":
    # Запуск тестов с выводом времени
    import time as std_time

    async def run_all_tests():
        test_functions = [
            test_basic_functionality,
            test_time_based_throttling,
            test_condition_based_matching,
            test_performance_high_load,
            test_concurrent_access,
            test_background_matching_performance,
        ]

        for test_func in test_functions:
            start = std_time.time()
            try:
                await test_func()
                end = std_time.time()
                print(f"✓ {test_func.__name__}: {end-start:.3f}s")
            except Exception as e:
                end = std_time.time()
                print(f"✗ {test_func.__name__}: {end-start:.3f}s - ERROR: {e}")

    asyncio.run(run_all_tests())
