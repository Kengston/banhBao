import os
import json
import aiofiles
from fastapi import FastAPI, Request, HTTPException
from aiogram import Bot, Dispatcher, types
from datetime import datetime, timedelta
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from typing import Dict, List, Optional

BOT_TOKEN = os.getenv("BOT_TOKEN")  # зададите в Render
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change-me")  # любой секрет
BASE_URL = os.getenv("RENDER_EXTERNAL_URL")  # Render задаст автоматически

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# Планировщик для напоминаний
scheduler = AsyncIOScheduler()

# Файл для хранения событий
EVENTS_FILE = "events.json"

# Структура события
class Event:
    def __init__(self, id: str, title: str, datetime_str: str, user_id: int, description: str = ""):
        self.id = id
        self.title = title
        self.datetime_str = datetime_str
        self.user_id = user_id
        self.description = description
        self.datetime = datetime.fromisoformat(datetime_str)
    
    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "datetime_str": self.datetime_str,
            "user_id": self.user_id,
            "description": self.description
        }
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            id=data["id"],
            title=data["title"],
            datetime_str=data["datetime_str"],
            user_id=data["user_id"],
            description=data.get("description", "")
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
            f"**Time:** {event.datetime.strftime('%H:%M, %d %b %Y')}\n"
            f"**In:** 10 minutes\n"
        )
        if event.description:
            reminder_text += f"**Description:** {event.description}\n"
        
        await bot.send_message(event.user_id, reminder_text, parse_mode="Markdown")
        print(f"Reminder sent for event: {event.title}")
    except Exception as e:
        print(f"Error sending reminder: {e}")

async def schedule_reminder(event: Event):
    """Планирует напоминание за 10 минут до события"""
    reminder_time = event.datetime - timedelta(minutes=10)
    
    # Планируем напоминание только если оно в будущем
    if reminder_time > datetime.now(pytz.timezone("Asia/Ho_Chi_Minh")):
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
@dp.message_handler(commands=["add_event"])
async def add_event(message: types.Message):
    """Добавляет новое событие в расписание"""
    args = message.get_args().strip()
    
    if not args:
        help_text = (
            "📅 **Add Event**\n\n"
            "Usage: `/add_event Title | YYYY-MM-DD HH:MM | Description`\n\n"
            "**Example:**\n"
            "`/add_event Team Meeting | 2024-01-15 14:30 | Discuss project progress`\n\n"
            "**Note:** Time is in Danang timezone (GMT+7)"
        )
        await message.reply(help_text, parse_mode="Markdown")
        return
    
    try:
        parts = args.split('|')
        if len(parts) < 2:
            raise ValueError("Invalid format")
        
        title = parts[0].strip()
        datetime_str = parts[1].strip()
        description = parts[2].strip() if len(parts) > 2 else ""
        
        # Парсим дату и время
        event_datetime = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
        # Конвертируем в часовой пояс Дананга
        tz = pytz.timezone("Asia/Ho_Chi_Minh")
        event_datetime = tz.localize(event_datetime)
        
        # Проверяем, что событие в будущем
        if event_datetime <= datetime.now(tz):
            await message.reply("❌ Event must be in the future!", parse_mode="Markdown")
            return
        
        # Создаем событие
        event_id = f"{message.from_user.id}_{int(event_datetime.timestamp())}"
        event = Event(
            id=event_id,
            title=title,
            datetime_str=event_datetime.isoformat(),
            user_id=message.from_user.id,
            description=description
        )
        
        # Сохраняем событие
        events[event_id] = event
        await save_events(events)
        
        # Планируем напоминание
        await schedule_reminder(event)
        
        success_text = (
            f"✅ **Event Added!**\n\n"
            f"**Title:** {title}\n"
            f"**Date & Time:** {event_datetime.strftime('%H:%M, %d %b %Y')}\n"
            f"**Reminder:** 10 minutes before\n"
        )
        if description:
            success_text += f"**Description:** {description}\n"
        
        await message.reply(success_text, parse_mode="Markdown")
        
    except ValueError as e:
        error_text = (
            "❌ **Invalid Format**\n\n"
            "Please use: `/add_event Title | YYYY-MM-DD HH:MM | Description`\n\n"
            "**Example:**\n"
            "`/add_event Team Meeting | 2024-01-15 14:30 | Discuss project progress`"
        )
        await message.reply(error_text, parse_mode="Markdown")
    except Exception as e:
        await message.reply(f"❌ Error adding event: {str(e)}", parse_mode="Markdown")

# Команда /list_events — список событий
@dp.message_handler(commands=["list_events"])
async def list_events(message: types.Message):
    """Показывает список событий пользователя"""
    user_events = [event for event in events.values() if event.user_id == message.from_user.id]
    
    if not user_events:
        await message.reply("📅 **No events scheduled**\n\nUse `/add_event` to create one!", parse_mode="Markdown")
        return
    
    # Сортируем по дате
    user_events.sort(key=lambda x: x.datetime)
    
    events_text = "📅 **Your Events:**\n\n"
    for i, event in enumerate(user_events, 1):
        events_text += f"**{i}.** {event.title}\n"
        events_text += f"   📅 {event.datetime.strftime('%H:%M, %d %b %Y')}\n"
        if event.description:
            events_text += f"   📝 {event.description}\n"
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
    
    if event_id in events and events[event_id].user_id == message.from_user.id:
        # Удаляем напоминание из планировщика
        try:
            scheduler.remove_job(f"reminder_{event_id}")
        except:
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
        "➕ `/add_event` - Add new event\n"
        "📋 `/list_events` - List your events\n"
        "🗑️ `/delete_event <ID>` - Delete event\n\n"
        "**Event Format:**\n"
        "`/add_event Title | YYYY-MM-DD HH:MM | Description`\n\n"
        "**Example:**\n"
        "`/add_event Team Meeting | 2024-01-15 14:30 | Discuss project progress`\n\n"
        "⏰ Reminders are sent 10 minutes before each event!"
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
    await bot.set_webhook(url)
    print(f"Webhook set to {url}")

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

@app.post(f"/webhook/{{secret}}")
async def telegram_update(secret: str, request: Request):
    # Проверяем секрет, чтобы не принимать чужие запросы
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="forbidden")

    data = await request.json()
    update = types.Update(**data)

    # ВАЖНО: проставляем текущие экземпляры для контекста aiogram v2
    Bot.set_current(bot)
    Dispatcher.set_current(dp)

    await dp.process_update(update)
    return {"ok": True}