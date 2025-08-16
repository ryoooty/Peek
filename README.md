# Peek
бот аналог C.ai но в телеграмме, с большим списком функций и лучшими нейронками под капотом

Требуется Python 3.10 или новее. Перед запуском установите зависимости (включая `aiohttp`) и задайте переменную окружения `DEEPSEEK_API_KEY`.

## Webhook endpoints

When the bot is running it also starts an `aiohttp` server on port `8080`.
External payment providers should use the following callback URLs:

| Provider       | URL                                          |
|----------------|----------------------------------------------|
| Boosty         | `POST http://<host>:8080/boosty/webhook`      |
| DonationAlerts | `POST http://<host>:8080/donationalerts/webhook` |

For testing the HTTP server in isolation you can still run
`python main.py`.
