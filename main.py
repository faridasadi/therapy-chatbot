import asyncio
import signal
import uvicorn
from app import app
from bot_handlers import create_bot_application
from re_engagement import run_re_engagement_system

async def run_api():
    config = uvicorn.Config(app, host="0.0.0.0", port=8000)
    server = uvicorn.Server(config)
    await server.serve()

async def shutdown(signal, loop):
    print(f"Received exit signal {signal.name}...")
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    [task.cancel() for task in tasks]
    print("Canceling outstanding tasks")
    await asyncio.gather(*tasks, return_exceptions=True)
    loop.stop()

def handle_exception(loop, context):
    msg = context.get("exception", context["message"])
    print(f"Error handling task: {msg}")
    print("Shutting down...")
    asyncio.create_task(shutdown(signal.SIGTERM, loop))

async def main():
    try:
        print("Starting Therapyyy Bot Server...")
        
        # Initialize components
        print("Initializing Telegram bot...")
        bot_app = create_bot_application()
        
        # Create FastAPI task
        api_task = asyncio.create_task(run_api())
        
        # Start the bot application
        print("Starting bot application...")
        await bot_app.application.initialize()
        await bot_app.application.start()
        
        # Create re-engagement task
        re_engagement_task = asyncio.create_task(
            run_re_engagement_system(bot_app.application.bot)
        )
        
        # Start updating
        async with bot_app.application:
            await bot_app.application.updater.start_polling()
            print("Bot is running...")
            
            # Wait for API and re-engagement tasks
            await asyncio.gather(api_task, re_engagement_task)
            
    except Exception as e:
        print(f"Fatal error in main loop: {e}")
        raise
    finally:
        print("Shutting down application...")
        if 'bot_app' in locals():
            await bot_app.application.stop()
            await bot_app.application.shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Shutting down gracefully...")