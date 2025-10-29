# Async Proxy Manager

Асинхронный менеджер прокси для Python с поддержкой `aiohttp` и `httpx`. Сделан за пару дней, может поможет кому-то)!

## ⚠️ Прозрачность о состоянии проекта

**Честно говоря, проект не доработан и имеет несколько существенных недостатков:**

- 🐛 **Тестирование**: Практически отсутствуют unit-тесты
- 📚 **Документация**: Многие методы не имеют docstrings
- 🎯 **Производительность**: Фоновая проверка прокси может быть оптимизирована
- 🧩 **Расширяемость**: Добавление новых типов прокси сложно

**Если вы хотите помочь с доработкой - буду рад пулл-реквестам! Особенно нужна помощь с:**

- Написанием тестов
- Оптимизацией очередей
- Улучшением обработки ошибок
- Документацией

## ✨ Особенности

- **🔧 Двойная поддержка** - `aiohttp` и `httpx` клиенты
- **🎯 Умные очереди** - с условиями и без
- **🛡️ SOCKS5 прокси** - полная аутентификация
- **📊 Мониторинг** - автоматическая проверка работоспособности
- **⏱️ Временные ограничения** - контроль частоты использования
- **🚀 Асинхронность** - полная поддержка async/await

## 📦 Установка

```bash
pip install aiohttp httpx aiohttp-socks

## Инициализация
```
from .proxy_controller import ProxyController, HttpClientType

# Менеджер с условиями
proxy_manager = await ProxyController.create_with_conditions(
    http_client=HttpClientType.httpx,
    with_check=True
)
```

## Добавление прокси
```
await proxy_manager.add_proxy(
    "192.168.1.1:1080:user:pass",
    conditions={"country": "US", "provider": "premium"}
)
```

## Использование
```
async with proxy_manager.acquire(
    task_key="web_scraping",
    time_condition=5.0,
    other_conditions={"country": "US"}
) as proxy_session:
    
    # Для httpx
    response = await proxy_session.session.get("https://api.example.com/data")
```

## Разные задачи
```
# Веб-скрапинг - частые запросы
async with proxy_manager.acquire(
    task_key="web_crawler",
    time_condition=2.0,
    other_conditions={"country": "US"}
) as proxy:
    pass

# API вызовы - редкие запросы  
async with proxy_manager.acquire(
    task_key="api_client", 
    time_condition=10.0,
    other_conditions={"country": "DE"}
) as proxy:
    pass
```

## Ручная проверка валидности прокси
```
is_working = await proxy_manager.manually_check_proxy("192.168.1.1:1080:user:pass")
```
