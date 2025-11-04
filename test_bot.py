#!/usr/bin/env python3
"""
Утилита для тестирования бота через long polling (без webhook)
"""
import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage

async def test_bot():
    bot_token = os.getenv("BOT_TOKEN", "8282626758:AAF9LHxgELgdC140o-H0fVGG_SBqIxCTt8I")
    
    if not bot_token:
        print("❌ BOT_TOKEN is not set!")
        return
    
    bot = Bot(token=bot_token)
    dp = Dispatcher(bot, storage=MemoryStorage())
    
    # Простой обработчик для теста
    @dp.message_handler(commands=["test", "help", "start", "info"])
    async def test_handler(message: types.Message):
        print(f"✅ Received command: {message.text}")
        await message.reply(f"✅ Bot is working! You sent: {message.text}")
    
    @dp.message_handler()
    async def echo_handler(message: types.Message):
        print(f"✅ Received message: {message.text}")
        await message.reply(f"Echo: {message.text}")
    
    print("🤖 Testing bot with long polling...")
    print(f"🔑 Bot token: {bot_token[:20]}...")
    
    try:
        # Проверяем информацию о боте
        me = await bot.get_me()
        print(f"✅ Bot info: @{me.username} ({me.first_name})")
        
        # Получаем информацию о webhook
        webhook_info = await bot.get_webhook_info()
        print(f"\n📡 Current webhook info:")
        print(f"  URL: {webhook_info.url}")
        print(f"  Pending updates: {webhook_info.pending_update_count}")
        print(f"  Last error: {webhook_info.last_error_message}")
        
        if webhook_info.url:
            print(f"\n⚠️  Webhook is set to: {webhook_info.url}")
            response = input("Delete webhook and use polling? (y/n): ")
            if response.lower() == 'y':
                await bot.delete_webhook(drop_pending_updates=True)
                print("✅ Webhook deleted")
            else:
                print("❌ Cannot use polling while webhook is active")
                await bot.session.close()
                return
        
        # Получаем последние обновления
        print(f"\n📥 Getting pending updates...")
        updates = await bot.get_updates(limit=10)
        print(f"✅ Found {len(updates)} pending updates")
        
        for update in updates:
            print(f"\n📨 Update {update.update_id}:")
            if update.message:
                print(f"  From: {update.message.from_user.id}")
                print(f"  Text: {update.message.text}")
        
        # Запускаем polling на 30 секунд
        print(f"\n🚀 Starting polling for 30 seconds...")
        print("Send any message to the bot to test!")
        
        async def on_startup(dp):
            print("✅ Polling started")
        
        async def on_shutdown(dp):
            print("🛑 Polling stopped")
        
        # Запускаем на 30 секунд
        try:
            await asyncio.wait_for(
                dp.start_polling(on_startup=on_startup, on_shutdown=on_shutdown),
                timeout=30
            )
        except asyncio.TimeoutError:
            print("\n⏰ Time's up!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await dp.storage.close()
        await bot.session.close()

if __name__ == "__main__":
    print("🧪 Bot Tester\n")
    print("=" * 50)
    asyncio.run(test_bot())

