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
        print("[Bot] Starting Therapyyy bot initialization...")
        bot_app = create_bot_application()
        print("[Bot] Bot application instance created")
        
        print("[Bot] Initializing bot application and handlers...")
        await bot_app.initialize()
        print("[Bot] Bot initialization completed successfully")
        
        print("[Bot] Starting bot in polling mode...")
        start_time = asyncio.get_event_loop().time()
        await bot_app.start()
        print("[Bot] Bot polling started successfully!")
        print("[Bot] Bot is now running and ready to handle commands!")
        
        # Keep the bot running and monitor its health
        while True:
            current_time = asyncio.get_event_loop().time()
            uptime = int(current_time - start_time)
            hours = uptime // 3600
            minutes = (uptime % 3600) // 60
            seconds = uptime % 60
            
            print(f"[Bot] Heartbeat - Uptime: {hours}h {minutes}m {seconds}s")
            print("[Bot] Polling is active, waiting for updates...")
            
            try:
                # Check if the bot is still responsive
                me = await bot_app.application.bot.get_me()
                print(f"[Bot] Bot health check passed - @{me.username} is responsive")
            except Exception as e:
                print(f"[Bot] Warning: Bot health check failed - {str(e)}")
                print("[Bot] Attempting to maintain connection...")
            
            await asyncio.sleep(300)  # Log heartbeat every 5 minutes
            
    except Exception as e:
        print(f"[Bot] CRITICAL ERROR - Bot initialization/runtime failed:")
        print(f"[Bot] Error type: {type(e).__name__}")
        print(f"[Bot] Error details: {str(e)}")
        if 'bot_app' in locals():
            print("[Bot] Attempting graceful shutdown...")
            try:
                await bot_app.stop()
                print("[Bot] Bot stopped successfully")
            except Exception as stop_error:
                print(f"[Bot] Error during shutdown: {str(stop_error)}")
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
