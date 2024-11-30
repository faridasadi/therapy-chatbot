import asyncio
from app import app
from bot_handlers import create_bot_application

async def run_bot():
    bot_app = create_bot_application()
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.run_polling()

def run_flask():
    app.run(host="0.0.0.0", port=8000)

if __name__ == "__main__":
    # Run Flask in a separate thread
    import threading
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    
    # Run the bot in the main thread
    asyncio.run(run_bot())
