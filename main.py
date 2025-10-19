import os
import json
import aiofiles
from fastapi import FastAPI, Request, HTTPException
from aiogram import Bot, Dispatcher, types
from datetime import datetime, timedelta
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from typing import Dict
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from urllib.parse import urlparse

# Единый часовой пояс приложения — строго Дананг
DANANG_TZ = pytz.timezone("Asia/Ho_Chi_Minh")

BOT_TOKEN = os.getenv("BOT_TOKEN")  # зададите в Render
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change-me")  # любой секрет
BASE_URL = os.getenv("RENDER_EXTERNAL_URL")  # Render задаст автоматически

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

# Планировщик для напоминаний (строго в часовом поясе Дананга)
scheduler = AsyncIOScheduler(timezone=pytz.timezone("Asia/Ho_Chi_Minh"))

# Файл для хранения событий
EVENTS_FILE = "events.json"

# Структура события
class Event:
    def __init__(self, id: str, title: str, datetime_str: str, chat_id: int, link: str = ""):
        self.id = id
        self.title = title
        self.datetime_str = datetime_str
        self.chat_id = chat_id
        self.link = link
        self.datetime = datetime.fromisoformat(datetime_str)
    
    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "datetime_str": self.datetime_str,
            "chat_id": self.chat_id,
            "link": self.link
        }
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            id=data["id"],
            title=data["title"],
            datetime_str=data["datetime_str"],
            chat_id=data.get("chat_id", data.get("user_id")),
            link=data.get("link", data.get("description", ""))
        )

# Загрузка и сохранение событий
async def load_events() -> Dict[str, Event]:
    """Загружает события из файла"""
    try:
        async with aiofiles.open(EVENTS_FILE, 'r', encoding='utf-8') as f:
            data = json.loads(await f.read())
            return {event_id: Event.from_dict(event_data) for event_id, event_data in data.items()}
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"Error loading events: {e}")
        return {}

async def save_events(events: Dict[str, Event]):
    """Сохраняет события в файл"""
    try:
        data = {event_id: event.to_dict() for event_id, event in events.items()}
        async with aiofiles.open(EVENTS_FILE, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(data, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"Error saving events: {e}")

# Глобальное хранилище событий
events: Dict[str, Event] = {}

async def send_reminder(event: Event):
    """Отправляет напоминание о событии"""
    try:
        reminder_text = (
            f"⏰ **Reminder!**\n\n"
            f"**Event:** {event.title}\n"
            f"**Time:** {event.datetime.astimezone(DANANG_TZ).strftime('%H:%M, %d %b %Y')}\n"
            f"**In:** 10 minutes\n"
        )
        if event.link:
            reminder_text += f"\n🔗 [Join meeting]({event.link})\n"
        
        await bot.send_message(event.chat_id, reminder_text, parse_mode="Markdown", disable_web_page_preview=True)
        print(f"Reminder sent for event: {event.title}")
    except Exception as e:
        print(f"Error sending reminder: {e}")

async def schedule_reminder(event: Event):
    """Планирует напоминание за 10 минут до события"""
    reminder_time = event.datetime - timedelta(minutes=10)
    
    # Планируем напоминание только если оно в будущем
    if reminder_time > datetime.now(DANANG_TZ):
        scheduler.add_job(
            send_reminder,
            trigger=DateTrigger(run_date=reminder_time),
            args=[event],
            id=f"reminder_{event.id}",
            replace_existing=True
        )
        print(f"Scheduled reminder for event {event.title} at {reminder_time}")

# Команда /time — точное время в Дананге
@dp.message_handler(commands=["time"])
async def send_time(message: types.Message):
    tz = pytz.timezone("Asia/Ho_Chi_Minh")
    now = datetime.now(tz)
    # Пример: 14:03:27, 19 Oct 2025 (GMT+7)
    offset_hours = int(now.utcoffset().total_seconds() // 3600)
    formatted = now.strftime("%H:%M:%S, %d %b %Y")
    # Делаем время жирным для лучшей видимости
    await message.reply(f"🕒 Current time in Danang: *{formatted}* (GMT{offset_hours:+d})", parse_mode="Markdown")

# Команда /links — ссылки на рабочие доски
@dp.message_handler(commands=["links"])
async def send_links(message: types.Message):
    links_text = (
        "🔗 **Useful Links:**\n\n"
        "📋 **Miro Board:**\n"
        "[Open Miro](https://miro.com/app/board/uXjVJ7CoXxM=/)\n\n"
        "🎯 **Jira Board:**\n"
        "[Open Jira](https://danildc.atlassian.net/jira/software/projects/KAN/boards/1)"
    )
    await message.reply(links_text, parse_mode="Markdown", disable_web_page_preview=True)

# Команда /add_event — добавление события
class AddEventStates(StatesGroup):
    waiting_for_datetime = State()
    waiting_for_title = State()
    waiting_for_link = State()

def _is_valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False

@dp.message_handler(commands=["add_event"])
async def add_event(message: types.Message, state: FSMContext):
    """Многошаговое создание события: дата/время -> название -> ссылка"""
    # Старт: просим дату и время в Дананге
    prompt = (
        "📅 **Create Event**\n\n"
        "Send date and time in Danang timezone (GMT+7) in format:\n"
        "`YYYY-MM-DD HH:MM`\n\n"
        "Example: `2025-10-19 21:30`"
    )
    sent = await message.reply(prompt, parse_mode="Markdown")
    await state.update_data(_msg_ids=[sent.message_id, message.message_id])
    await AddEventStates.waiting_for_datetime.set()

@dp.message_handler(state=AddEventStates.waiting_for_datetime, content_types=types.ContentTypes.TEXT)
async def add_event_datetime_step(message: types.Message, state: FSMContext):
    text = message.text.strip()
    try:
        naive_dt = datetime.strptime(text, "%Y-%m-%d %H:%M")
        event_dt = DANANG_TZ.localize(naive_dt)
        if event_dt <= datetime.now(DANANG_TZ):
            raise ValueError("past")
        data = await state.get_data()
        msg_ids = data.get("_msg_ids", []) + [message.message_id]
        await state.update_data(event_dt=event_dt.isoformat(), _msg_ids=msg_ids)
        sent = await message.reply("📝 Now send the event title", parse_mode="Markdown")
        await state.update_data(_msg_ids=msg_ids + [sent.message_id])
        await AddEventStates.waiting_for_title.set()
    except Exception:
        err = await message.reply("❌ Invalid datetime. Use `YYYY-MM-DD HH:MM` in Danang time.", parse_mode="Markdown")
        data = await state.get_data()
        await state.update_data(_msg_ids=(data.get("_msg_ids", []) + [message.message_id, err.message_id]))

@dp.message_handler(state=AddEventStates.waiting_for_title, content_types=types.ContentTypes.TEXT)
async def add_event_title_step(message: types.Message, state: FSMContext):
    title = message.text.strip()
    if not title:
        err = await message.reply("❌ Title cannot be empty. Send the title.")
        data = await state.get_data()
        await state.update_data(_msg_ids=(data.get("_msg_ids", []) + [message.message_id, err.message_id]))
        return
    data = await state.get_data()
    msg_ids = data.get("_msg_ids", []) + [message.message_id]
    await state.update_data(title=title, _msg_ids=msg_ids)
    sent = await message.reply("🔗 Send the meeting link (http/https)")
    await state.update_data(_msg_ids=msg_ids + [sent.message_id])
    await AddEventStates.waiting_for_link.set()

@dp.message_handler(state=AddEventStates.waiting_for_link, content_types=types.ContentTypes.TEXT)
async def add_event_link_step(message: types.Message, state: FSMContext):
    link = message.text.strip()
    if not _is_valid_url(link):
        err = await message.reply("❌ Invalid URL. Send a valid http/https link.")
        data = await state.get_data()
        await state.update_data(_msg_ids=(data.get("_msg_ids", []) + [message.message_id, err.message_id]))
        return
    data = await state.get_data()
    msg_ids = data.get("_msg_ids", []) + [message.message_id]
    event_dt_iso = data.get("event_dt")
    title = data.get("title")
    event_dt = datetime.fromisoformat(event_dt_iso)
    event_id = f"{message.chat.id}_{int(event_dt.timestamp())}"
    event = Event(
        id=event_id,
        title=title,
        datetime_str=event_dt.isoformat(),
        chat_id=message.chat.id,
        link=link
    )
    # Сохраняем
    events[event_id] = event
    await save_events(events)
    # Планируем напоминание
    await schedule_reminder(event)

    # Удаляем промежуточные сообщения
    try:
        for mid in set(msg_ids):
            try:
                await bot.delete_message(chat_id=message.chat.id, message_id=mid)
            except Exception:
                pass
    finally:
        pass

    # Итоговое сообщение-только одно
    final_text = (
        "✅ **Event Created!**\n\n"
        f"**Title:** {title}\n"
        f"**Date & Time (Danang):** {event_dt.astimezone(DANANG_TZ).strftime('%H:%M, %d %b %Y')}\n"
        f"🔗 [Join meeting]({link})\n"
        "⏰ Reminder will be sent 10 minutes before."
    )
    await message.reply(final_text, parse_mode="Markdown", disable_web_page_preview=True)
    await state.finish()

# Команда /list_events — список событий
@dp.message_handler(commands=["list_events"])
async def list_events(message: types.Message):
    """Показывает список событий пользователя"""
    user_events = [event for event in events.values() if event.chat_id == message.chat.id]
    
    if not user_events:
        await message.reply("📅 **No events scheduled**\n\nUse `/add_event` to create one!", parse_mode="Markdown")
        return
    
    # Сортируем по дате
    user_events.sort(key=lambda x: x.datetime)
    
    events_text = "📅 **Your Events:**\n\n"
    for i, event in enumerate(user_events, 1):
        events_text += f"**{i}.** {event.title}\n"
        events_text += f"   📅 {event.datetime.strftime('%H:%M, %d %b %Y')}\n"
        # Описание убрано; показываем, есть ли ссылка
        events_text += f"   🔗 {('link attached' if event.link else 'no link')}\n"
        events_text += f"   🆔 `{event.id}`\n\n"
    
    events_text += "Use `/delete_event <ID>` to remove an event"
    
    await message.reply(events_text, parse_mode="Markdown")

# Команда /delete_event — удаление события
@dp.message_handler(commands=["delete_event"])
async def delete_event(message: types.Message):
    """Удаляет событие по ID"""
    event_id = message.get_args().strip()
    
    if not event_id:
        await message.reply("❌ Please provide event ID\n\nUse `/list_events` to see your events", parse_mode="Markdown")
        return
    
    if event_id in events and events[event_id].chat_id == message.chat.id:
        # Удаляем напоминание из планировщика
        try:
            scheduler.remove_job(f"reminder_{event_id}")
        except Exception:
            pass
        
        # Удаляем событие
        event_title = events[event_id].title
        del events[event_id]
        await save_events(events)
        
        await message.reply(f"✅ **Event deleted:** {event_title}", parse_mode="Markdown")
    else:
        await message.reply("❌ Event not found or you don't have permission to delete it", parse_mode="Markdown")

# Команда /help — справка по всем командам
@dp.message_handler(commands=["help"])
async def help_command(message: types.Message):
    """Показывает справку по всем доступным командам"""
    help_text = (
        "🤖 **Bot Commands:**\n\n"
        "🕒 `/time` - Current time in Danang\n"
        "🔗 `/links` - Useful links (Miro, Jira)\n\n"
        "📅 **Event Management:**\n"
        "➕ `/add_event` - Create new event (step-by-step)\n"
        "📋 `/list_events` - List your events\n"
        "🗑️ `/delete_event <ID>` - Delete event\n\n"
        "Creation flow: send datetime (Danang) -> title -> meeting link.\n\n"
        "⏰ Reminders are sent 10 minutes before each event with the link!"
    )
    await message.reply(help_text, parse_mode="Markdown")

app = FastAPI()

@app.on_event("startup")
async def on_startup():
    # Загружаем сохраненные события
    global events
    events = await load_events()
    print(f"Loaded {len(events)} events from storage")
    
    # Планируем напоминания для всех загруженных событий
    for event in events.values():
        await schedule_reminder(event)
    
    # Запускаем планировщик
    scheduler.start()
    print("Scheduler started")
    
    # Путь вебхука с секретом
    webhook_path = f"/webhook/{WEBHOOK_SECRET}"
    if not BASE_URL:
        # На первом старте Render может не прокинуть env
        print("WARNING: RENDER_EXTERNAL_URL is empty; webhook won't be set automatically.")
        return
    url = BASE_URL.rstrip("/") + webhook_path
    # Сбрасываем висящие обновления и явно ограничиваем типы
    await bot.set_webhook(url, drop_pending_updates=True, allowed_updates=["message", "callback_query"])
    info = await bot.get_webhook_info()
    print(f"Webhook set to {url}")
    try:
        print(f"Webhook info: pending={info.pending_update_count}, last_error={getattr(info, 'last_error_message', None)}")
    except Exception:
        pass

@app.on_event("shutdown")
async def on_shutdown():
    # Останавливаем планировщик
    scheduler.shutdown()
    print("Scheduler stopped")
    
    await bot.delete_webhook()
    # аккуратно закрываем HTTP-сессию aiogram
    await bot.session.close()

@app.get("/")
async def health():
    return {"ok": True}

@app.post("/webhook/{secret}")
async def telegram_update(secret: str, request: Request):
    # Проверяем секрет, чтобы не принимать чужие запросы
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="forbidden")

    data = await request.json()
    # Простой лог для диагностики
    try:
        print("Incoming update keys:", list(data.keys()))
    except Exception:
        pass
    # Парсинг апдейта для aiogram v2
    update = types.Update(**data)

    # ВАЖНО: проставляем текущие экземпляры для контекста aiogram v2
    Bot.set_current(bot)
    Dispatcher.set_current(dp)

    try:
        await dp.process_update(update)
    except Exception as e:
        print("Error processing update:", repr(e))
    return {"ok": True}