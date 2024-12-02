import asyncio
import signal
import uvicorn
from bot_handlers import create_bot_application
from re_engagement import run_re_engagement_system
from context_manager import start_context_management
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
        
        # Initialize components
        print("Initializing Telegram bot...")
        bot_app = create_bot_application()
        
        # Initialize the application with retry logic
        retry_count = 3
        while retry_count > 0:
            try:
                print(f"Attempting to initialize bot (attempts remaining: {retry_count})")
                await asyncio.wait_for(bot_app.application.initialize(), timeout=30.0)
                await bot_app.application.start()
                print("Bot successfully initialized and started")
                break
            except asyncio.TimeoutError:
                retry_count -= 1
                if retry_count > 0:
                    print("Initialization timed out, retrying...")
                    await asyncio.sleep(5)
                else:
                    print("Failed to initialize bot after multiple attempts")
                    raise
            except Exception as e:
                print(f"Error initializing bot: {str(e)}")
                raise
        
        # Create other tasks
        tasks = [
            asyncio.create_task(run_api()),
            # Temporarily disabled re-engagement system
            # asyncio.create_task(run_re_engagement_system(bot_app.application.bot)),
            asyncio.create_task(start_context_management())
        ]
        
        # Run tasks concurrently
        await asyncio.gather(*tasks)
            
    except Exception as e:
        print(f"Fatal error in main loop: {e}")
        raise
    finally:
        if 'bot_app' in locals():
            try:
                await bot_app.application.stop()
                await bot_app.application.shutdown()
            except Exception as e:
                print(f"Error during shutdown: {e}")

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
