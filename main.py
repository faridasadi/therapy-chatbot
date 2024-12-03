import asyncio
import signal
import logging
from typing import Optional
from bot_handlers import create_bot_application
from re_engagement import run_re_engagement_system
from context_manager import start_context_management

# Configure logging
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
    
    for task in tasks:
        task.cancel()
    
    logger.info(f"Cancelling {len(tasks)} outstanding tasks")
    await asyncio.gather(*tasks, return_exceptions=True)
    loop.stop()

def handle_exception(loop, context):
    """Global exception handler for the event loop"""
    msg = context.get("exception", context["message"])
    logger.error(f"Error handling task: {msg}")
    logger.info("Shutting down due to exception...")
    asyncio.create_task(shutdown(signal.SIGTERM, loop))

async def main():
    """Main application entry point with simplified event loop handling"""
    bot_app = None
    try:
        logger.info("Starting Telegram Therapy Bot...")
        bot_app = create_bot_application()
        
        # Initialize bot and create tasks
        await bot_app.initialize()
        logger.info("Bot initialization successful")
        
        tasks = [
            asyncio.create_task(start_context_management(), name="context_management"),
            asyncio.create_task(run_re_engagement_system(bot_app.application.bot), name="re_engagement"),
            asyncio.create_task(bot_app.application.updater.start_polling(), name="bot_polling")
        ]
        
        # Wait for tasks to complete or for shutdown signal
        await asyncio.gather(*tasks)
        
    except Exception as e:
        logger.error(f"Critical error in main loop: {str(e)}")
        raise
    finally:
        if bot_app:
            try:
                await bot_app.stop()
                logger.info("Bot stopped successfully")
            except Exception as e:
                logger.error(f"Error during bot shutdown: {e}")

if __name__ == "__main__":
    try:
        # Set up the event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.set_exception_handler(handle_exception)
        
        # Handle shutdown signals
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(shutdown(s, loop))
            )
        
        # Run the main application
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error(f"Unhandled exception: {e}")
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()
        except Exception:
            pass
        logger.info("Event loop closed")