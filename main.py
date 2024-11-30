import asyncio
import signal
from hypercorn.asyncio import serve
from hypercorn.config import Config
from app import app
from bot_handlers import create_bot_application

async def run_flask():
    config = Config()
    config.bind = ["0.0.0.0:8000"]
    await serve(app, config)

async def run_bot():
    try:
        print("Starting Therapyyy bot initialization...")
        bot_app = create_bot_application()
        print("Bot application created, initializing...")
        await bot_app.initialize()
        print("Bot initialization completed successfully")
        print("Starting bot...")
        await bot_app.start()
        print("Bot is now running and ready to handle commands!")
        
        # Keep the bot running
        while True:
            print("Bot heartbeat - Still running")
            await asyncio.sleep(300)  # Log heartbeat every 5 minutes
            
    except Exception as e:
        print(f"CRITICAL ERROR - Bot initialization failed: {e}")
        if 'bot_app' in locals():
            await bot_app.stop()
        raise

async def cleanup(signal_=None):
    if signal_:
        print(f"Received exit signal {signal_.name}...")
    print("Cleaning up...")
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    [task.cancel() for task in tasks]
    print("Waiting for tasks to complete...")
    await asyncio.gather(*tasks, return_exceptions=True)
    print("Cleanup completed")

async def main():
    # Setup signal handlers
    loop = asyncio.get_event_loop()
    signals = (signal.SIGHUP, signal.SIGTERM, signal.SIGINT)
    for s in signals:
        loop.add_signal_handler(
            s,
            lambda s=s: asyncio.create_task(cleanup(signal_=s))
        )

    try:
        # Start both Flask and bot
        await asyncio.gather(
            run_flask(),
            run_bot(),
            return_exceptions=True
        )
    except Exception as e:
        print(f"Fatal error in main loop: {e}")
    finally:
        await cleanup()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Shutting down gracefully...")
