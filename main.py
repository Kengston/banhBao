import os
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from datetime import datetime
import pytz
import asyncio

BOT_TOKEN = os.getenv("BOT_TOKEN")  # зададите в Render
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change-me")  # любой секрет
BASE_URL = os.getenv("RENDER_EXTERNAL_URL")  # Render задаст автоматически

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# Команда /time — точное время в Дананге
@dp.message_handler(commands=["time"])
async def send_time(message: types.Message):
    tz = pytz.timezone("Asia/Ho_Chi_Minh")
    now = datetime.now(tz)
    # Пример: 14:03:27, 19 Oct 2025 (GMT+7)
    offset_hours = int(now.utcoffset().total_seconds() // 3600)
    formatted = now.strftime("%H:%M:%S, %d %b %Y")
    await message.reply(f"🕒 Текущее время в Дананге: {formatted} (GMT{offset_hours:+d})")

app = FastAPI()

@app.on_event("startup")
async def on_startup():
    # Путь вебхука с секретом
    webhook_path = f"/webhook/{WEBHOOK_SECRET}"
    if not BASE_URL:
        # На первом старте Render может не прокинуть env, можно задать вручную
        # или повторно деплоить; но попытаемся без BASE_URL не ставить хук.
        print("WARNING: RENDER_EXTERNAL_URL is empty; webhook won't be set automatically.")
        return
    url = BASE_URL.rstrip("/") + webhook_path
    await bot.set_webhook(url)
    print(f"Webhook set to {url}")

@app.on_event("shutdown")
async def on_shutdown():
    await bot.delete_webhook()

@app.get("/")
async def health():
    return {"ok": True}

@app.post(f"/webhook/{{secret}}")
async def telegram_update(secret: str, request: Request):
    # Проверяем секрет, чтобы не принимать чужие запросы
    if secret != WEBHOOK_SECRET:
        return {"status": "forbidden"}
    data = await request.json()
    update = types.Update(**data)
    await dp.process_update(update)
    return {"ok": True}