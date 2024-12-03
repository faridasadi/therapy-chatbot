import asyncio
import os
import signal
import logging
from typing import Optional
from bot_handlers import create_bot_application
from re_engagement import run_re_engagement_system
from context_manager import start_context_management
from aiohttp import web
from monitoring import log_metrics_periodically, pipeline_monitor
import config

# Ensure logs directory exists
os.makedirs('logs', exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler('logs/bot.log'),
        logging.StreamHandler()
    ]
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
    """Main application entry point with enhanced event loop and webhook handling"""
    bot_app = None
    tasks = []
    try:
        logger.info("Starting Telegram Therapy Bot...")
        bot_app = create_bot_application()
        
        # Initialize bot
        await bot_app.initialize()
        logger.info("Bot initialization successful")
        
        if config.USE_WEBHOOK:
            logger.info(f"Starting bot in webhook mode on port {config.WEBHOOK_PORT}")
            webhook_path = "telegram"
            webhook_url = f"{config.WEBHOOK_URL}/{webhook_path}"
            
            # Start webhook server with retry mechanism
            max_retries = 5
            base_delay = 2
            
            for attempt in range(max_retries):
                try:
                    # Setup webhook first
                    await bot_app.setup_webhook()
                    
                    # Create and setup webhook application
                    web_app = await bot_app.create_webhook_app(
                        webhook_path=webhook_path,
                        webhook_url=webhook_url
                    )
                    
                    runner = web.AppRunner(web_app)
                    await runner.setup()
                    site = web.TCPSite(runner, "0.0.0.0", config.WEBHOOK_PORT)
                    await site.start()
                    logger.info(f"Webhook server started at {webhook_url}")
                    break
                    
                except Exception as e:
                    if "429" in str(e) and attempt < max_retries - 1:  # Rate limit error
                        delay = base_delay * (2 ** attempt)
                        logger.warning(f"Rate limit hit. Retrying webhook setup in {delay} seconds...")
                        await asyncio.sleep(delay)
                        continue
                    raise
        else:
            logger.info("Starting bot in polling mode")
            await bot_app.application.updater.start_polling(drop_pending_updates=True)
        
        # Create and start background tasks
        tasks = [
            asyncio.create_task(start_context_management(), name="context_management"),
            asyncio.create_task(run_re_engagement_system(bot_app.application.bot), name="re_engagement"),
            asyncio.create_task(log_metrics_periodically(interval=30), name="metrics_logging"),
        ]
        
        # Wait indefinitely while handling tasks
        await asyncio.gather(*tasks, return_exceptions=True)
        
    except Exception as e:
        logger.error(f"Critical error in main loop: {str(e)}")
        raise
    finally:
        if tasks:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            
        if bot_app:
            if config.USE_WEBHOOK:
                await bot_app.application.bot.delete_webhook()
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