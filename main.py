import asyncio
import signal
import uvicorn
from bot_handlers import create_bot_application
from re_engagement import run_re_engagement_system
from app import app

async def run_api():
    """Run the FastAPI application"""
    config = uvicorn.Config(app, host="0.0.0.0", port=8000)
    server = uvicorn.Server(config)
    await server.serve()

async def shutdown(signal_type, loop):
    """Handle graceful shutdown"""
    print(f"Received exit signal {signal_type.name}...")
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    [task.cancel() for task in tasks]
    await asyncio.gather(*tasks, return_exceptions=True)
    loop.stop()

def handle_exception(loop, context):
    """Global exception handler"""
    print(f"Error handling task: {context.get('exception', context['message'])}")
    asyncio.create_task(shutdown(signal.SIGTERM, loop))

async def main():
    """Main application entry point"""
    try:
        print("Starting Therapyyy Bot Server...")
        
        # Initialize bot
        bot_app = create_bot_application()
        await bot_app.application.initialize()
        
        # Create tasks for all components
        tasks = [
            run_api(),
            run_re_engagement_system(bot_app.application.bot),
            bot_app.application.updater.start_polling()
        ]
        
        # Run all tasks concurrently
        await asyncio.gather(*tasks)
        
    except Exception as e:
        print(f"Fatal error in main loop: {e}")
        raise
    finally:
        if 'bot_app' in locals():
            await bot_app.stop()

if __name__ == "__main__":
    try:
        # Set up exception handling
        loop = asyncio.get_event_loop()
        loop.set_exception_handler(handle_exception)
        
        # Handle shutdown signals
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(shutdown(s, loop))
            )
        
        # Run the application
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Shutting down gracefully...")
