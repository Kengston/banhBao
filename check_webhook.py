#!/usr/bin/env python3
"""
Скрипт для проверки и переустановки webhook для Telegram бота
"""
import os
import asyncio
import sys
from aiogram import Bot

async def check_and_set_webhook():
    bot_token = os.getenv("BOT_TOKEN")
    webhook_secret = os.getenv("WEBHOOK_SECRET", "change-me")
    base_url = os.getenv("RENDER_EXTERNAL_URL")
    
    if not bot_token:
        print("❌ BOT_TOKEN is not set!")
        return
    
    print(f"🔑 BOT_TOKEN: {bot_token[:10]}...")
    print(f"🔐 WEBHOOK_SECRET: {webhook_secret}")
    print(f"🌐 BASE_URL: {base_url}")
    print()
    
    bot = Bot(token=bot_token)
    
    try:
        # Получаем текущую информацию о webhook
        print("📡 Checking current webhook status...")
        info = await bot.get_webhook_info()
        
        print("\n📋 Current webhook info:")
        print(f"  URL: {info.url}")
        print(f"  Pending updates: {info.pending_update_count}")
        print(f"  Last error date: {info.last_error_date}")
        print(f"  Last error message: {info.last_error_message}")
        print(f"  Max connections: {info.max_connections}")
        print(f"  Allowed updates: {info.allowed_updates}")
        print()
        
        # Если URL не пустой, спрашиваем, нужно ли переустановить
        if info.url:
            print(f"⚠️  Webhook already set to: {info.url}")
            if len(sys.argv) > 1 and sys.argv[1] == "--reset":
                print("🔄 Resetting webhook...")
            else:
                print("\nTo reset webhook, run: python check_webhook.py --reset")
                await bot.session.close()
                return
        
        # Устанавливаем новый webhook
        if base_url:
            webhook_url = f"{base_url.rstrip('/')}/webhook/{webhook_secret}"
            print(f"🔧 Setting webhook to: {webhook_url}")
            
            result = await bot.set_webhook(
                webhook_url,
                drop_pending_updates=True,
                allowed_updates=["message", "callback_query"]
            )
            
            if result:
                print("✅ Webhook set successfully!")
                
                # Проверяем еще раз
                info = await bot.get_webhook_info()
                print(f"\n📋 New webhook info:")
                print(f"  URL: {info.url}")
                print(f"  Pending updates: {info.pending_update_count}")
            else:
                print("❌ Failed to set webhook!")
        else:
            print("❌ BASE_URL (RENDER_EXTERNAL_URL) is not set!")
            print("\nTo delete webhook, run: python check_webhook.py --delete")
            
        # Опция для удаления webhook
        if len(sys.argv) > 1 and sys.argv[1] == "--delete":
            print("🗑️  Deleting webhook...")
            result = await bot.delete_webhook(drop_pending_updates=True)
            if result:
                print("✅ Webhook deleted successfully!")
            else:
                print("❌ Failed to delete webhook!")
                
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await bot.session.close()

if __name__ == "__main__":
    print("🤖 Telegram Webhook Checker\n")
    print("=" * 50)
    asyncio.run(check_and_set_webhook())

