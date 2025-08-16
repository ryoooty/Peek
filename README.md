# Peek
бот аналог C.ai но в телеграмме, с большим списком функций и лучшими нейронками под капотом

Требуется Python 3.10 или новее. Перед запуском установите зависимости (включая `aiohttp`) и задайте переменную окружения `DEEPSEEK_API_KEY`.

## Webhook endpoints

The HTTP server exposes the following webhook URLs for payment providers:

| Provider         | Path                    |
|------------------|-------------------------|
| Boosty           | `POST /boosty/webhook`  |
| DonationAlerts   | `POST /donationalerts/webhook` |

Run `python main.py` to start a simple `aiohttp` server with these routes.
