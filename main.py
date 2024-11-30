import asyncio
import signal
import uvicorn
from app import app
from bot_handlers import create_bot_application
from error_logging import error_logger
from error_handlers import handle_bot_error, handle_web_error

async def run_api():
    try:
        config = uvicorn.Config(app, host="0.0.0.0", port=8080)
        server = uvicorn.Server(config)
        await server.serve()
    except Exception as e:
        error_id = handle_web_error(e, {'component': 'api_server'})
        print(f"Critical API server error (Error ID: {error_id})")
        raise

async def run_bot():
    bot_app = None
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
        error_id = handle_bot_error(e, context={'stage': 'bot_initialization'})
        print(f"[Bot] CRITICAL ERROR (Error ID: {error_id})")
        if bot_app:
            print("[Bot] Attempting graceful shutdown...")
            try:
                await bot_app.stop()
                print("[Bot] Bot stopped successfully")
            except Exception as stop_error:
                error_id = handle_bot_error(stop_error, context={'stage': 'shutdown'})
                print(f"[Bot] Error during shutdown (Error ID: {error_id})")
        raise

async def shutdown(signal, loop):
    print(f"Received exit signal {signal.name}...")
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    [task.cancel() for task in tasks]
    print("Canceling outstanding tasks")
    await asyncio.gather(*tasks, return_exceptions=True)
    loop.stop()

def handle_exception(loop, context):
    error = context.get("exception", context["message"])
    error_id = error_logger.log_error(
        error=error,
        component='event_loop',
        severity='CRITICAL',
        context={'loop_context': str(context)}
    )
    print(f"Critical error in event loop (Error ID: {error_id})")
    print("Initiating shutdown...")
    asyncio.create_task(shutdown(signal.SIGTERM, loop))

async def main():
    bot_app = None
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
        print("Starting API server...")
        api_task = asyncio.create_task(run_api())
        
        # Ensure clean webhook state and proper cleanup
        print("Starting cleanup process...")
        cleanup_bot = None
        try:
            print("Starting cleanup process...")
            cleanup_bot = None
            bot_info = None

            # Initialize cleanup bot
            try:
                print("Initializing cleanup bot...")
                cleanup_bot = create_bot_application()
                
                # Initialize bot with proper state checks
                if not cleanup_bot.is_initialized:
                    await cleanup_bot.initialize()
                    print("Cleanup bot initialized")
                
                # Get bot info to verify connection
                if cleanup_bot.bot:
                    try:
                        bot_info = await cleanup_bot.bot.get_me()
                        print(f"Connected as {bot_info.username} for cleanup")
                    except Exception as e:
                        error_id = handle_bot_error(
                            e,
                            context={
                                'stage': 'cleanup_init',
                                'action': 'verify_connection',
                                'is_initialized': cleanup_bot.is_initialized,
                                'has_bot': bool(cleanup_bot.bot)
                            }
                        )
                        print(f"Warning: Failed to verify bot connection (Error ID: {error_id})")
                else:
                    print("Warning: Bot instance not available during cleanup")
            except Exception as init_error:
                error_id = handle_bot_error(
                    init_error,
                    context={
                        'stage': 'cleanup_init',
                        'action': 'initialize_bot',
                        'critical': False
                    }
                )
                print(f"Warning: Cleanup bot initialization failed (Error ID: {error_id})")
            
            # Clean up webhook if bot is available
            try:
                if cleanup_bot and cleanup_bot.bot and cleanup_bot.is_initialized:
                    print("Attempting to delete webhook...")
                    try:
                        await cleanup_bot.bot.delete_webhook(drop_pending_updates=True)
                        print("Successfully deleted webhook")
                    except Exception as webhook_error:
                        error_id = handle_bot_error(
                            webhook_error,
                            context={
                                'stage': 'cleanup_webhook',
                                'action': 'delete_webhook',
                                'critical': False,
                                'bot_info': bot_info.to_dict() if bot_info else None,
                                'bot_state': {
                                    'is_initialized': cleanup_bot.is_initialized,
                                    'is_running': cleanup_bot.is_running,
                                    'has_bot': bool(cleanup_bot.bot)
                                }
                            }
                        )
                        print(f"Warning: Webhook cleanup error (Error ID: {error_id})")
                else:
                    print("Skipping webhook deletion - bot not in correct state")
                    print(f"Bot state: initialized={cleanup_bot.is_initialized if cleanup_bot else False}, "
                          f"has_bot={bool(cleanup_bot.bot) if cleanup_bot else False}")
            except Exception as e:
                error_id = handle_bot_error(
                    e,
                    context={
                        'stage': 'cleanup_webhook',
                        'action': 'webhook_cleanup_wrapper',
                        'critical': False
                    }
                )
                print(f"Warning: Error in webhook cleanup process (Error ID: {error_id})")
            
            # Give time for webhook deletion to propagate
            await asyncio.sleep(2)
            
            # Enhanced cleanup of existing application state
            if cleanup_bot and cleanup_bot.application:
                app_state = "unknown"
                try:
                    # Check application state with more detailed verification
                    app_state = "running" if getattr(cleanup_bot.application, 'running', False) or \
                              getattr(cleanup_bot.application.updater, '_running', False) else "not_running"
                    
                    if app_state == "running":
                        # Force stop any existing polling
                        if hasattr(cleanup_bot.application.updater, '_running') and \
                           cleanup_bot.application.updater._running:
                            try:
                                await cleanup_bot.application.updater.stop()
                                print("Stopped existing updater polling")
                            except Exception as e:
                                error_id = handle_bot_error(
                                    e,
                                    context={'stage': 'cleanup_polling', 'action': 'stop_updater'}
                                )
                                print(f"Warning: Polling stop error (Error ID: {error_id})")
                        
                        # Attempt graceful stop
                        try:
                            await cleanup_bot.application.stop()
                            print("Stopped previous bot instance")
                        except Exception as e:
                            error_id = handle_bot_error(
                                e,
                                context={'stage': 'cleanup_stop', 'action': 'stop_application'}
                            )
                            print(f"Warning: Stop error (Error ID: {error_id})")
                        
                        # Force cleanup
                        try:
                            await cleanup_bot.application.shutdown()
                            print("Completed application shutdown")
                        except Exception as e:
                            error_id = handle_bot_error(
                                e,
                                context={'stage': 'cleanup_shutdown', 'action': 'shutdown_application'}
                            )
                            print(f"Warning: Shutdown error (Error ID: {error_id})")
                            
                        # Additional cleanup delay
                        await asyncio.sleep(5)
                        print("Successfully completed cleanup sequence")
                    else:
                        print("No running bot instance detected")
                        
                except Exception as stop_error:
                    error_id = handle_bot_error(
                        stop_error,
                        context={
                            'stage': 'cleanup_shutdown',
                            'action': 'complete_cleanup',
                            'critical': True,
                            'application_state': app_state,
                            'bot_info': bot_info.to_dict() if bot_info else None
                        }
                    )
                    print(f"Critical cleanup error (Error ID: {error_id})")
                    # Force additional delay on error
                    await asyncio.sleep(10)
            
            print("Cleanup process completed successfully")
            
        except Exception as e:
            error_id = handle_bot_error(
                e,
                context={
                    'stage': 'cleanup',
                    'critical': True,
                    'cleanup_state': 'failed',
                    'bot_info': bot_info.to_dict() if bot_info else None
                }
            )
            print(f"Warning during cleanup (Error ID: {error_id})")
        finally:
            if cleanup_bot:
                try:
                    # Only attempt shutdown if the application exists and is initialized
                    if cleanup_bot.application and cleanup_bot.is_initialized:
                        if cleanup_bot.is_running:
                            try:
                                await cleanup_bot.stop()
                                print("Cleanup bot stopped successfully")
                            except Exception as e:
                                error_id = handle_bot_error(
                                    e,
                                    context={
                                        'stage': 'cleanup_finally',
                                        'action': 'stop_bot',
                                        'critical': False
                                    }
                                )
                                print(f"Warning: Error stopping cleanup bot (Error ID: {error_id})")
                        
                        try:
                            await cleanup_bot.application.shutdown()
                            print("Cleanup bot shutdown completed")
                        except Exception as e:
                            error_id = handle_bot_error(
                                e,
                                context={
                                    'stage': 'cleanup_finally',
                                    'action': 'shutdown_application',
                                    'critical': False
                                }
                            )
                            print(f"Warning: Error during cleanup shutdown (Error ID: {error_id})")
                    else:
                        print("Skipping cleanup bot shutdown - not initialized or no application")
                except Exception as e:
                    error_id = handle_bot_error(
                        e,
                        context={
                            'stage': 'cleanup_finally',
                            'action': 'final_cleanup',
                            'critical': False
                        }
                    )
                    print(f"Warning: Error in final cleanup (Error ID: {error_id})")
                
            # Increased delay to ensure proper cleanup
            await asyncio.sleep(5)  # Increased delay before new instance
        
        # Initialize and start the bot with fresh instance
        print("Initializing Telegram bot...")
        bot_app = create_bot_application()
        try:
            await bot_app.initialize()
            
            # Import re-engagement system
            from re_engagement import run_re_engagement_system
            
            print("Starting Telegram bot...")
            await bot_app.start()
            
            # Start re-engagement system
            print("Starting re-engagement system...")
            re_engagement_task = asyncio.create_task(run_re_engagement_system(bot_app.bot))
            
            print("All systems initialized successfully")
            
            # Keep the main loop running
            while True:
                await asyncio.sleep(1)
                
        except Exception as e:
            error_id = handle_bot_error(e, context={'stage': 'main_loop'})
            print(f"Critical error in main loop (Error ID: {error_id})")
            raise
            
    except KeyboardInterrupt:
        print("Received shutdown signal...")
    except Exception as e:
        error_id = handle_bot_error(e, context={'stage': 'main'})
        print(f"Fatal error (Error ID: {error_id})")
        raise
    finally:
        print("Shutting down...")
        if bot_app:
            try:
                await bot_app.stop()
            except Exception as e:
                error_id = handle_bot_error(e, context={'stage': 'final_shutdown'})
                print(f"Error during final shutdown (Error ID: {error_id})")
        
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
    except Exception as e:
        error_id = handle_bot_error(e, context={'stage': 'startup'})
        print(f"Fatal startup error (Error ID: {error_id})")
        raise
