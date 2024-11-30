import asyncio
import signal
import uvicorn
from app import app
from bot_handlers import create_bot_application

async def run_api():
    config = uvicorn.Config(app, host="0.0.0.0", port=8000)
    server = uvicorn.Server(config)
    await server.serve()

async def run_bot():
    try:
        print("[Bot] Starting Therapyyy bot initialization...")
        bot_app = create_bot_application()
        print("[Bot] Bot application instance created")
        
        print("[Bot] Initializing bot application and handlers...")
        await bot_app.initialize()
        print("[Bot] Bot initialization completed successfully")
        
        print("[Bot] Starting bot polling...")
        await bot_app.start()
        
    except Exception as e:
        print(f"[Bot] CRITICAL ERROR:")
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
        
        # Create the event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Set up signal handlers
        signals = (signal.SIGHUP, signal.SIGTERM, signal.SIGINT)
        for s in signals:
            loop.add_signal_handler(
                s, lambda s=s: asyncio.create_task(shutdown(s, loop))
            )
        
        # Set up exception handler
        loop.set_exception_handler(handle_exception)
        
        # Start FastAPI in the background
        api_task = asyncio.create_task(run_api())
        
        # Initialize and start the bot
        print("Initializing Telegram bot...")
        bot_app = create_bot_application()
        await bot_app.initialize()
        
        # Run the bot
        print("Starting Telegram bot...")
        await bot_app.start()
        
        # Keep the main loop running
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        print("Received shutdown signal...")
    except Exception as e:
        print(f"Fatal error in main loop: {e}")
        raise
    finally:
        print("Shutting down...")
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        [task.cancel() for task in tasks]
        print("Waiting for tasks to complete...")
        await asyncio.gather(*tasks, return_exceptions=True)
        loop.stop()
        loop.close()
        print("Cleanup completed")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Shutting down gracefully...")
