import asyncio
import signal
import logging
from typing import Optional
from bot_handlers import create_bot_application
from re_engagement import run_re_engagement_system
from context_manager import start_context_management

# Configure logging with optimized format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

async def shutdown(signal_type, loop):
    """Handle graceful shutdown"""
    logger.info(f"Received exit signal {signal_type.name}...")
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    [task.cancel() for task in tasks]
    await asyncio.gather(*tasks, return_exceptions=True)
    loop.stop()

def handle_exception(loop, context):
    """Global exception handler"""
    logger.error(f"Error handling task: {context.get('exception', context['message'])}")
    asyncio.create_task(shutdown(signal.SIGTERM, loop))

async def main():
    """Main application entry point for Telegram bot"""
    try:
        logger.info("Starting Telegram Therapy Bot...")
        
        # Initialize Telegram bot with optimized retry logic
        bot_app = create_bot_application()
        retry_count = 3
        
        while retry_count > 0:
            try:
                logger.info(f"Initializing bot (attempts: {retry_count})")
                await asyncio.wait_for(bot_app.application.initialize(), timeout=15.0)
                await bot_app.application.start()
                logger.info("Bot initialization successful")
                break
            except asyncio.TimeoutError:
                retry_count -= 1
                if retry_count > 0:
                    logger.warning("Timeout occurred, retrying...")
                    await asyncio.sleep(3)
                else:
                    raise
            except Exception as e:
                logger.error(f"Bot initialization failed: {str(e)}")
                raise
        
        # Run core bot tasks
        await asyncio.gather(
            run_re_engagement_system(bot_app.application.bot),
            start_context_management()
        )
            
    except Exception as e:
        logger.error(f"Critical error in main loop: {e}")
        raise
    finally:
        if 'bot_app' in locals():
            try:
                await bot_app.application.stop()
                await bot_app.application.shutdown()
            except Exception as e:
                logger.error(f"Shutdown error: {e}")

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
        logger.info("Shutting down gracefully...")
