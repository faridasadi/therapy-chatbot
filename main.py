import asyncio
from threading import Thread
from telegram import Update
from app import app
from bot_handlers import create_bot_application

def run_flask():
    app.run(host="0.0.0.0", port=8000)

async def run_bot():
    bot_app = create_bot_application()
    await bot_app.initialize()
    try:
        await bot_app.start()
    except Exception as e:
        print(f"Bot error: {e}")
        await bot_app.stop()

def run_async_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_bot())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()

def run_flask_in_thread():
    Thread(target=run_flask, daemon=True).start()

async def main_loop():
    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    # Start Flask in a separate thread
    run_flask_in_thread()
    
    # Run the bot in a separate thread with its own event loop
    bot_thread = Thread(target=run_async_bot, daemon=True)
    bot_thread.start()
    
    try:
        # Create a new event loop for the main thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        # Run the main loop
        loop.run_until_complete(main_loop())
    except KeyboardInterrupt:
        print("Shutting down gracefully...")
    finally:
        loop.close()
