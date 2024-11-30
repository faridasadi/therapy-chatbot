import os
from datetime import datetime
from telegram import Update, Chat, User as TelegramUser
from error_handlers import bot_error_handler, handle_bot_error
from telegram.error import NetworkError, TimedOut, BadRequest, Forbidden
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import TelegramError, NetworkError, TimedOut, BadRequest, Forbidden
from telegram.constants import ChatAction
from config import TELEGRAM_TOKEN, WELCOME_MESSAGE, HELP_MESSAGE, SUBSCRIPTION_PROMPT
from models import Message, User
from ai_service import get_therapy_response
from database import get_db_session, get_or_create_user
from database import check_subscription_status, increment_message_count, save_message
from error_logging import error_logger
import asyncio
from contextlib import asynccontextmanager

class BotApplication:
    def __init__(self):
        self.application = None
        self.bot = None
        self.debug_mode = True
        self._initialized = False
        self._running = False
        
    def debug_print(self, message: str):
        """Helper method for debug prints"""
        if self.debug_mode:
            timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
            print(f"[Debug {timestamp}] {message}")
            
    @property
    def is_initialized(self):
        """Check if the bot is properly initialized."""
        return self._initialized and self.application is not None
        
    @property
    def is_running(self):
        """Check if the bot is currently running."""
        return self._running and self.is_initialized and getattr(self.application, 'running', False)

    async def initialize(self):
        """Initialize the bot with enhanced error handling and state tracking."""
        if self.is_initialized:
            self.debug_print("Bot is already initialized")
            return

        self.debug_print("Starting bot initialization...")
        initialization_error = None
        
        try:
            # Verify bot token
            if not TELEGRAM_TOKEN:
                raise ValueError("ERROR: Telegram token is empty!")
            
            token_preview = TELEGRAM_TOKEN[:6] + "..." + TELEGRAM_TOKEN[-4:]
            self.debug_print(f"Using bot token: {token_preview}")
            
            # Initialize application and bot
            self.application = Application.builder().token(TELEGRAM_TOKEN).build()
            self.bot = self.application.bot
            
            # Verify bot connection and identity
            try:
                bot_info = await self.bot.get_me()
                self.debug_print(f"Connected as: @{bot_info.username}")
                self.debug_print(f"Bot ID: {bot_info.id}")
                self.debug_print(f"Bot name: {bot_info.first_name}")
            except TelegramError as e:
                initialization_error = e
                error_id = error_logger.log_error(
                    error=e,
                    component='bot_handlers',
                    severity='ERROR',
                    context={'stage': 'initialization', 'action': 'verify_identity'}
                )
                self.debug_print(f"Failed to verify bot identity (Error ID: {error_id})")
                raise RuntimeError(f"Failed to verify bot connection: {str(e)}")
            
            # Explicitly disable webhook with retry logic
            max_retries = 3
            retry_count = 0
            while retry_count < max_retries:
                try:
                    await self.bot.delete_webhook(drop_pending_updates=True)
                    self.debug_print("Webhook disabled successfully")
                    break
                except Exception as e:
                    retry_count += 1
                    if retry_count == max_retries:
                        initialization_error = e
                        error_id = error_logger.log_error(
                            error=e,
                            component='bot_handlers',
                            severity='ERROR',
                            context={
                                'stage': 'initialization',
                                'action': 'disable_webhook',
                                'retry_count': retry_count
                            }
                        )
                        self.debug_print(f"Failed to disable webhook after {retry_count} attempts (Error ID: {error_id})")
                        raise
                    await asyncio.sleep(1)
            
            # Register handlers
            self.debug_print("Registering command handlers...")
            
            # Add update logger (highest priority)
            self.application.add_handler(MessageHandler(filters.ALL, self.log_update), -1)
            
            # Add command handlers
            self.application.add_handler(CommandHandler("start", self.start_command))
            self.application.add_handler(CommandHandler("help", self.help_command))
            self.application.add_handler(CommandHandler("subscribe", self.subscribe_command))
            self.application.add_handler(CommandHandler("status", self.status_command))
            
            self.application.add_handler(CommandHandler("testerror", self.test_error_command))
            # Add message handler
            self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
            
            # Add error handler
            self.application.add_error_handler(self.error_handler)
            
            # Set initialization flag only after everything is successful
            self._initialized = True
            self.debug_print("Bot initialization completed successfully")
            
        except Exception as e:
            # Reset application state in case of failure
            self._initialized = False
            self._running = False
            self.application = None
            self.bot = None
            
            # Log the error with enhanced context
            if not initialization_error:
                initialization_error = e
            
            error_id = error_logger.log_error(
                error=initialization_error,
                component='bot_handlers',
                severity='ERROR',
                context={
                    'stage': 'initialization',
                    'action': 'complete_init',
                    'initialized': self._initialized,
                    'running': self._running
                }
            )
            self.debug_print(f"Critical initialization error (Error ID: {error_id})")
            raise

    @staticmethod
    async def log_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Log any update received from Telegram."""
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
        
        try:
            user_id = update.effective_user.id if update.effective_user else "Unknown"
            update_type = "Unknown"
            update_id = update.update_id if hasattr(update, 'update_id') else "No ID"
            
            if update.message:
                if update.message.text:
                    if update.message.text.startswith('/'):
                        update_type = f"Command: {update.message.text.split()[0]}"
                    else:
                        update_type = "Text Message"
                elif update.message.photo:
                    update_type = "Photo"
                elif update.message.document:
                    update_type = "Document"
                elif update.message.voice:
                    update_type = "Voice"
            elif update.callback_query:
                update_type = "Callback Query"
            elif update.pre_checkout_query:
                update_type = "Pre-Checkout Query"
            
            print(f"\n[Update Log {timestamp}]")
            print(f"Update ID: {update_id}")
            print(f"Type: {update_type}")
            print(f"User ID: {user_id}")
            print(f"Raw Update Object:")
            print(f"{update.to_dict()}")
            
            return True
            
        except Exception as e:
            print(f"[Error {timestamp}] Failed to log update:")
            print(f"Error type: {type(e).__name__}")
            print(f"Error details: {str(e)}")
            return False
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.debug_print(f"Start command received from user {update.effective_user.id}")
        try:
            user = get_or_create_user(
                update.effective_user.id,
                update.effective_user.username,
                update.effective_user.first_name
            )
            await update.message.reply_text(WELCOME_MESSAGE)
            self.debug_print(f"Start command completed for user {update.effective_user.id}")
        except Exception as e:
            self.debug_print(f"Error in start command: {str(e)}")
            await update.message.reply_text("An error occurred. Please try again.")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.debug_print(f"Help command received from user {update.effective_user.id}")
        try:
            await update.message.reply_text(HELP_MESSAGE)
            self.debug_print(f"Help command completed for user {update.effective_user.id}")
        except Exception as e:
            self.debug_print(f"Error in help command: {str(e)}")
            await update.message.reply_text("An error occurred. Please try again.")

    async def subscribe_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.debug_print(f"Subscribe command received from user {update.effective_user.id}")
        try:
            user_id = update.effective_user.id
            user = get_or_create_user(user_id)
            
            db = get_db_session()
            try:
                user.subscription_prompt_views += 1
                db.commit()
            finally:
                db.close()
            
            await update.message.reply_text(SUBSCRIPTION_PROMPT)
            self.debug_print(f"Subscribe command completed for user {user_id}")
        except Exception as e:
            self.debug_print(f"Error in subscribe command: {str(e)}")
            await update.message.reply_text(
                "An unexpected error occurred. Please try again later."
            )

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.debug_print(f"Status command received from user {update.effective_user.id}")
        try:
            user_id = update.effective_user.id
            user = get_or_create_user(user_id)
            
            if check_subscription_status(user_id):
                message = "You have an active subscription with unlimited messages! 🌟"
            else:
                remaining = max(0, 20 - user.messages_count)
                weekly_remaining = max(0, 20 - user.weekly_messages_count)
                message = f"""Your current status:
        - Free messages remaining: {remaining}
        - Weekly free messages remaining: {weekly_remaining}
                """
            
            await update.message.reply_text(message)
            self.debug_print(f"Status command completed for user {user_id}")
        except Exception as e:
            self.debug_print(f"Error in status command: {str(e)}")
            await update.message.reply_text("An error occurred. Please try again.")
    @bot_error_handler
    async def test_error_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Command to test different error scenarios."""
        self.debug_print(f"Test error command received from user {update.effective_user.id}")
        
        error_type = update.message.text.split()[1] if len(update.message.text.split()) > 1 else "general"
        
        if error_type == "network":
            raise NetworkError("Simulated network error for testing")
        elif error_type == "timeout":
            raise TimedOut("Simulated timeout error for testing")
        elif error_type == "badrequest":
            raise BadRequest("Simulated bad request error for testing")
        elif error_type == "forbidden":
            raise Forbidden("Simulated forbidden error for testing")
        else:
            raise Exception("Simulated general error for testing")


    

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
        
        # Initial message receipt validation
        try:
            if not update.effective_user:
                self.debug_print(f"ERROR: No effective user in update")
                return
                
            if not update.message:
                self.debug_print(f"ERROR: No message in update")
                return
                
            user_id = update.effective_user.id
            message_text = update.message.text
            message_id = update.message.message_id
            
            self.debug_print(f"Message processing started:")
            self.debug_print(f"Message ID: {message_id}")
            self.debug_print(f"From User: {user_id}")
            self.debug_print(f"Content Length: {len(message_text) if message_text else 0}")
            
        except Exception as e:
            self.debug_print(f"CRITICAL: Failed to extract message details: {str(e)}")
            return
        
        try:
            # Send typing indicator immediately
            try:
                await context.bot.send_chat_action(
                    chat_id=update.effective_chat.id,
                    action="typing"
                )
                self.debug_print("Sent typing indicator")
            except Exception as e:
                self.debug_print(f"Error sending typing indicator: {str(e)}")

            # Test database connection
            try:
                user = get_or_create_user(user_id)
                self.debug_print(f"Database connection verified - User found/created")
            except Exception as e:
                self.debug_print(f"Database connection test failed: {str(e)}")
                raise
            
            # Save incoming message
            try:
                save_message(user_id, message_text, True)
                self.debug_print(f"Saved incoming message")
            except Exception as e:
                self.debug_print(f"Error saving message: {str(e)}")
                raise
            
            # Check message limits
            try:
                can_respond, remaining = increment_message_count(user_id)
                self.debug_print(f"Message limit check: can_respond={can_respond}, remaining={remaining}")
                
                if not can_respond:
                    self.debug_print(f"User reached message limit")
                    db = get_db_session()
                    try:
                        user = db.query(User).get(user_id)
                        if user:
                            user.subscription_prompt_views += 1
                            db.commit()
                    finally:
                        db.close()
                    await update.message.reply_text(SUBSCRIPTION_PROMPT)
                    return
            except Exception as e:
                self.debug_print(f"Error checking message limits: {str(e)}")
                raise
            
            # Get AI response with theme analysis
            try:
                self.debug_print(f"Requesting AI response with personalization")
                # Get AI response
                response, theme, sentiment = get_therapy_response(message_text, user_id)
                self.debug_print("Got AI response")
                
                # Update message with theme and sentiment
                try:
                    db = get_db_session()
                    latest_message = (db.query(Message)
                        .filter(Message.user_id == user_id)
                        .order_by(Message.timestamp.desc())
                        .first())
                    if latest_message:
                        latest_message.theme = theme
                        latest_message.sentiment_score = sentiment
                        db.commit()
                finally:
                    db.close()
                
                
            except Exception as e:
                self.debug_print(f"Error getting AI response: {str(e)}")
                raise
            
            # Save bot response with theme
            try:
                save_message(user_id, response, False)
                self.debug_print(f"Saved bot response")
            except Exception as e:
                self.debug_print(f"Error saving bot response: {str(e)}")
                raise
            
            # Send response
            try:
                await update.message.reply_text(response)
                self.debug_print(f"Sent AI response")
            except TelegramError as e:
                self.debug_print(f"Error sending response: {str(e)}")
                raise
            
            # Notify about remaining messages
            if 0 < remaining <= 5:
                try:
                    self.debug_print(f"Sending remaining messages notification: {remaining}")
                    await update.message.reply_text(
                        f"You have {remaining} free messages remaining. "
                        "Consider subscribing for unlimited access!"
                    )
                except TelegramError as e:
                    self.debug_print(f"Error sending remaining messages notification: {str(e)}")
                
        except Exception as e:
            # Log error with context using the new error logger
            context = {
                'user_id': update.effective_user.id,
                'message_length': len(message_text) if message_text else 0,
                'message_id': message_id,
                'timestamp': datetime.utcnow().isoformat()
            }
            
            error_id = error_logger.log_error(
                error=e,
                component='message_processing',
                severity='ERROR',
                context=context
            )
            
            self.debug_print(f"Error logged with ID: {error_id}")
            
            try:
                # Send user-friendly error message with reference ID
                error_message = error_logger.get_user_message(error_id)
                await update.message.reply_text(error_message)
                
            except TelegramError as send_error:
                self.debug_print(f"Failed to send error message: {str(send_error)}")
                self.debug_print("Attempting alternative error notification...")
                
                try:
                    # Attempt to send a simplified message
                    await update.message.reply_text("An error occurred. Please try again later.")
                except:
                    self.debug_print("Failed to send any error notification to user")
            
            finally:
                self.debug_print("="*50)

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced error handler for the Telegram bot with improved error categorization and recovery."""
        error = context.error
        
        try:
            # Prepare detailed error context
            error_context = {
                'update': update.to_dict() if update else None,
                'user_id': update.effective_user.id if update and update.effective_user else None,
                'chat_id': update.effective_chat.id if update and update.effective_chat else None,
                'timestamp': datetime.utcnow().isoformat(),
                'error_type': type(error).__name__,
                'command': update.message.text if update and update.message else None
            }
            
            # Enhanced error categorization and handling
            severity = 'ERROR'
            recovery_action = None
            user_message = None
            
            if isinstance(error, NetworkError):
                severity = 'WARNING'
                error_context['category'] = 'network_error'
                recovery_action = 'retry'
                user_message = (
                    "I'm experiencing connection issues. "
                    "Your message will be processed once the connection is restored."
                )
                
            elif isinstance(error, TimedOut):
                severity = 'WARNING'
                error_context['category'] = 'timeout'
                recovery_action = 'retry'
                user_message = (
                    "The request timed out. Please try again. "
                    "If this persists, try sending shorter messages."
                )
                
            elif isinstance(error, BadRequest):
                severity = 'ERROR'
                error_context['category'] = 'bad_request'
                recovery_action = 'ignore'
                user_message = (
                    "I couldn't process that request. "
                    "Please make sure your message is valid."
                )
                
            elif isinstance(error, Forbidden):
                severity = 'WARNING'
                error_context['category'] = 'forbidden'
                recovery_action = 'block'
                self.debug_print(f"Bot was blocked by user {error_context['user_id']}")
                return  # No message needed as user blocked the bot
                
            else:
                severity = 'ERROR'
                error_context['category'] = 'unknown'
                recovery_action = 'report'
            
            # Add recovery information to context
            error_context['recovery_action'] = recovery_action
            
            # Log the error with enhanced context
            error_id = error_logger.log_error(
                error=error,
                component='telegram_bot',
                severity=severity,
                context=error_context
            )
            
            # Attempt recovery based on action type
            if recovery_action == 'retry' and update and update.message:
                try:
                    # Queue message for retry
                    self.debug_print(f"Queueing message {update.message.message_id} for retry")
                    # Note: Implement message queue mechanism if needed
                    pass
                except Exception as retry_error:
                    self.debug_print(f"Failed to queue message for retry: {str(retry_error)}")
            
            # Send appropriate error message to user
            if update and update.effective_message and user_message:
                try:
                    if not user_message:
                        user_message = error_logger.get_user_message(error_id, severity)
                    
                    await update.effective_message.reply_text(
                        f"{user_message}\nReference ID: {error_id}"
                    )
                except TelegramError as msg_error:
                    self.debug_print(f"Failed to send error message: {str(msg_error)}")
            
        except Exception as e:
            # If error handler itself fails, log it as critical
            error_id = error_logger.log_error(
                error=e,
                component='error_handler',
                severity='CRITICAL',
                context={
                    'original_error': str(error),
                    'handler_error': str(e),
                    'handler_state': 'failed'
                }
            )
            self.debug_print(f"Critical error in error handler: {error_id}")

    async def start(self):
        """Start the bot with improved state management."""
        if not self.is_initialized:
            raise RuntimeError("Cannot start: Bot is not initialized")
            
        if self.is_running:
            self.debug_print("Bot is already running")
            return
            
        self.debug_print("Starting bot...")
        try:
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
            self._running = True
            self.debug_print("Bot started successfully!")
        except Exception as e:
            self._running = False
            error_id = error_logger.log_error(
                error=e,
                component='bot_handlers',
                severity='ERROR',
                context={
                    'action': 'start_bot',
                    'initialization_state': self.is_initialized,
                    'running_state': self._running
                }
            )
            self.debug_print(f"Error starting bot (Error ID: {error_id})")
            raise

    async def stop(self):
        """Stop the bot with comprehensive error handling and state management."""
        if not self.is_initialized:
            self.debug_print("Bot was never initialized, nothing to stop")
            return

        if not self.application:
            self.debug_print("No application instance exists, nothing to stop")
            return
            
        if not self.is_running and not getattr(self.application, 'running', False):
            self.debug_print("Application is not running, skipping stop operation")
            return
            
        self.debug_print("Stopping bot...")
        shutdown_error = None
        initial_state = {
            'was_initialized': self.is_initialized,
            'was_running': self.is_running,
            'application_running': getattr(self.application, 'running', False),
            'updater_running': getattr(self.application.updater, '_running', False) if self.application and hasattr(self.application, 'updater') else False
        }
        
        try:
            # Only attempt to stop if the application exists and is actually running
            if self.application and (initial_state['application_running'] or initial_state['updater_running']):
                # Stop polling first if it's running
                if initial_state['updater_running']:
                    try:
                        await self.application.updater.stop()
                        self.debug_print("Stopped polling successfully")
                    except Exception as e:
                        shutdown_error = e
                        error_id = error_logger.log_error(
                            error=e,
                            component='bot_handlers',
                            severity='WARNING',
                            context={
                                'action': 'stop_polling',
                                'state': initial_state
                            }
                        )
                        self.debug_print(f"Warning: Error stopping polling (Error ID: {error_id})")

                # Attempt graceful application stop
                try:
                    if initial_state['application_running']:
                        await self.application.stop()
                        self.debug_print("Bot stopped successfully")
                except Exception as e:
                    if not shutdown_error:
                        shutdown_error = e
                    error_id = error_logger.log_error(
                        error=e,
                        component='bot_handlers',
                        severity='WARNING',
                        context={
                            'action': 'stop_application',
                            'state': initial_state
                        }
                    )
                    self.debug_print(f"Warning: Error stopping application (Error ID: {error_id})")
            
            # Always attempt to shutdown the application
            try:
                if self.application:
                    await self.application.shutdown()
                    self.debug_print("Application shutdown completed")
            except Exception as e:
                if not shutdown_error:
                    shutdown_error = e
                error_id = error_logger.log_error(
                    error=e,
                    component='bot_handlers',
                    severity='WARNING',
                    context={
                        'action': 'shutdown_application',
                        'state': initial_state
                    }
                )
                self.debug_print(f"Warning: Error during shutdown (Error ID: {error_id})")
            
            # Reset state regardless of errors
            self._running = False
            self._initialized = False
            
            # Log final status
            if shutdown_error:
                error_id = error_logger.log_error(
                    error=shutdown_error,
                    component='bot_handlers',
                    severity='WARNING',
                    context={
                        'action': 'stop_bot',
                        'initial_state': initial_state,
                        'final_state': {
                            'is_initialized': self.is_initialized,
                            'is_running': self.is_running,
                            'application_running': getattr(self.application, 'running', False) if self.application else False
                        }
                    }
                )
                self.debug_print(f"Non-critical error during bot shutdown (Error ID: {error_id})")
            
        except Exception as e:
            error_id = error_logger.log_error(
                error=e,
                component='bot_handlers',
                severity='ERROR',
                context={
                    'action': 'stop_bot',
                    'critical': True,
                    'state': {
                        'was_initialized': True,
                        'was_running': True,
                        'is_initialized': self.is_initialized,
                        'is_running': self.is_running
                    }
                }
            )
            self.debug_print(f"Critical error during bot shutdown (Error ID: {error_id})")
            raise

def create_bot_application():
    return BotApplication()