import os
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackContext
)
from database import get_db_session, engine
from models import User, Base
from ai_service import get_therapy_response
from datetime import datetime
from config import WELCOME_MESSAGE, HELP_MESSAGE

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BotApplication:
    def __init__(self):
        """Initialize bot application"""
        logger.info("Initializing bot application")
        self.token = os.environ.get('TELEGRAM_BOT_TOKEN')
        if not self.token:
            raise ValueError("TELEGRAM_BOT_TOKEN not found in environment variables")
        
        self.application = Application.builder().token(self.token).build()
        logger.info("Bot application created")

    async def handle_message(self, update: Update, context: CallbackContext):
        """Handle incoming messages"""
        try:
            user_id = update.effective_user.id
            username = update.effective_user.username
            first_name = update.effective_user.first_name
            
            logger.info(f"Processing message from user {user_id}")
            
            # Get or create user record with verification
            with get_db_session() as db:
                # Verify database connection
                db.execute(text("SELECT 1"))
                
                user = db.query(User).get(user_id)
                if not user:
                    user = User(
                        id=user_id,
                        username=username,
                        first_name=first_name,
                        joined_at=datetime.utcnow(),
                        messages_count=0,
                        weekly_messages_count=0,
                        last_message_reset=datetime.utcnow()
                    )
                    db.add(user)
                    db.commit()
                    logger.info(f"Created new user record for user {user_id}")
                    
                # Verify user record
                db.refresh(user)
                logger.info(f"User record verified for user {user_id}")

            # Process message and get response
            response, theme, sentiment = await get_therapy_response(
                update.message.text,
                user_id
            )
            
            await update.message.reply_text(response)
            logger.info(f"Sent response to user {user_id}")
            
        except Exception as e:
            logger.error(f"Error handling message: {str(e)}")
            await update.message.reply_text(
                "I apologize, but I'm having trouble processing your message. "
                "Please try again in a moment."
            )

    async def start_command(self, update: Update, context: CallbackContext):
        """Handle /start command"""
        try:
            await update.message.reply_text(WELCOME_MESSAGE)
            logger.info(f"Sent welcome message to user {update.effective_user.id}")
        except Exception as e:
            logger.error(f"Error in start command: {str(e)}")
            await update.message.reply_text("An error occurred. Please try again.")

    async def help_command(self, update: Update, context: CallbackContext):
        """Handle /help command"""
        try:
            await update.message.reply_text(HELP_MESSAGE)
        except Exception as e:
            logger.error(f"Error in help command: {str(e)}")
            await update.message.reply_text("An error occurred. Please try again.")

    async def subscribe_command(self, update: Update, context: CallbackContext):
        """Handle /subscribe command"""
        subscription_text = (
            "💎 Premium Features:\n\n"
            "- Unlimited conversations\n"
            "- Priority response time\n"
            "- Enhanced conversation memory\n\n"
            "Contact our support team for subscription details."
        )
        await update.message.reply_text(subscription_text)

    async def status_command(self, update: Update, context: CallbackContext):
        """Handle /status command"""
        user_id = update.effective_user.id
        with get_db_session() as db:
            user = db.query(User).get(user_id)
            if user:
                status = (
                    f"📊 Your Status:\n\n"
                    f"Messages this week: {user.weekly_messages_count}\n"
                    f"Total messages: {user.messages_count}\n"
                    f"Subscription: {'Active' if user.is_subscribed else 'Free tier'}"
                )
                if user.is_subscribed and user.subscription_end:
                    status += f"\nSubscription ends: {user.subscription_end.strftime('%Y-%m-%d')}"
            else:
                status = "Sorry, I couldn't find your user information."
        await update.message.reply_text(status)

    async def error_handler(self, update: object, context: CallbackContext):
        """Handle errors"""
        logger.error(f"Error handling update: {context.error}")

    async def initialize(self):
        """Initialize bot handlers"""
        logger.info("Starting bot handler initialization")
        
        try:
            # Verify database connection first
            with get_db_session() as db:
                db.execute(text("SELECT 1"))
                logger.info("Database connection verified")
            
            # Create database tables if they don't exist
            Base.metadata.create_all(bind=engine)
            logger.info("Database tables verified")
            
            # Clear existing handlers to prevent duplicates
            if hasattr(self.application, 'handlers'):
                self.application.handlers.clear()
                logger.info("Cleared existing handlers")
            
            # Register command handlers
            handlers = [
                ("start", self.start_command),
                ("help", self.help_command),
                ("subscribe", self.subscribe_command),
                ("status", self.status_command)
            ]
            
            for command, handler in handlers:
                self.application.add_handler(CommandHandler(command, handler))
                logger.info(f"Registered /{command} command handler")
            
            # Register message handler with verification
            message_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
            self.application.add_handler(message_handler)
            logger.info("Registered message handler")
            
            # Register error handler
            self.application.add_error_handler(self.error_handler)
            logger.info("Registered error handler")
            
            # Initialize application
            await self.application.initialize()
            logger.info("Bot application initialized")
            
            # Verify handler registration
            if not self.application.handlers:
                logger.error("No handlers registered after initialization")
                raise RuntimeError("Handler registration failed")
            
            logger.info(f"Successfully registered {len(self.application.handlers[0])} handlers")
            return True
            
        except Exception as e:
            logger.error(f"Initialization failed: {str(e)}")
            raise

    async def start(self):
        """Start the bot with polling"""
        try:
            await self.application.run_polling(drop_pending_updates=True)
        except Exception as e:
            logger.error(f"Bot startup failed: {str(e)}")
            raise

    async def stop(self):
        """Stop the bot"""
        if self.application:
            await self.application.shutdown()

def create_bot_application():
    return BotApplication()

                
                await update.message.reply_text(welcome_text)
                
        except Exception as e:
            print(f"[Error] Start command failed: {str(e)}")
            await update.message.reply_text("I apologize, but I encountered a temporary issue. Please try /start again.")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            await update.message.reply_text(HELP_MESSAGE)
        except Exception as e:
            print(f"[Error] Help command failed: {str(e)}")
            await update.message.reply_text("An error occurred. Please try again.")

    async def subscribe_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_user:
            return

        user_id = update.effective_user.id
        async with db_session() as db:
            try:
                user = get_or_create_user(user_id)
                user.subscription_prompt_views += 1
                db.commit()
                await update.message.reply_text(SUBSCRIPTION_PROMPT)
            except Exception as e:
                print(f"[Error] Subscribe command failed: {str(e)}")
                await update.message.reply_text("An unexpected error occurred. Please try again later.")

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_user:
            return

        try:
            status_message = await self.get_status_message(update.effective_user.id)
            await update.message.reply_text(status_message)
        except Exception as e:
            print(f"[Error] Status command failed: {str(e)}")
            await update.message.reply_text("An error occurred. Please try again.")

    async def clearnow_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Hidden command to delete all user data"""
        if not update.effective_user:
            return

        user_id = update.effective_user.id
        print("[Debug] Clearnow command received from user:", user_id)
        try:
            await update.message.reply_text("🔄 Processing your data deletion request...")
            
            # Delete all user data
            from database import delete_user_data
            success = delete_user_data(user_id)
            
            if success:
                await update.message.reply_text(
                    "✅ All your data has been successfully deleted.\n"
                    "You can start fresh by using the /start command."
                )
            else:
                await update.message.reply_text(
                    "❌ Sorry, there was an error processing your request.\n"
                    "Please try again later or contact support."
                )
                
        except Exception as e:
            print(f"[Error] Clearnow command failed: {str(e)}")
            await update.message.reply_text(
                "An unexpected error occurred while processing your request.\n"
                "Please try again later."
            )

    async def handle_background_collection(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, message_text: str):
        async with db_session() as db:
            try:
                user = db.query(User).get(user_id)
                current_step = context.user_data.get('background_step', 'age')

                if current_step == 'age':
                    try:
                        age = int(message_text)
                        if 13 <= age <= 100:
                            user.age = age
                            context.user_data['background_step'] = 'gender'
                            await update.message.reply_text(
                                "Thank you! What gender do you identify as?\n"
                                "You can type:\n"
                                "- Male\n"
                                "- Female\n"
                                "- Prefer not to say")
                        else:
                            await update.message.reply_text("Please enter a valid age between 13 and 100.")
                    except ValueError:
                        await update.message.reply_text("Please enter a valid number for your age.")

                elif current_step == 'gender':
                    valid_genders = ['male', 'female', 'non-binary', 'prefer not to say']
                    if message_text.lower() in valid_genders:
                        user.gender = message_text.lower()
                        context.user_data['background_step'] = 'therapy_experience'
                        await update.message.reply_text(
                            "Have you ever been to therapy before?\n"
                            "Please choose:\n"
                            "- Never\n"
                            "- Currently in therapy\n"
                            "- Had therapy in the past")
                    else:
                        await update.message.reply_text("Please select one of the provided options.")

                elif current_step == 'therapy_experience':
                    valid_experiences = ['never', 'currently in therapy', 'had therapy in the past']
                    if message_text.lower() in valid_experiences:
                        user.therapy_experience = message_text.lower()
                        context.user_data['background_step'] = 'primary_concerns'
                        await update.message.reply_text(
                            "Last question: What are your primary concerns or reasons for seeking support? "
                            "Please briefly describe them.")
                    else:
                        await update.message.reply_text("Please select one of the provided options.")

                elif current_step == 'primary_concerns':
                    user.primary_concerns = message_text
                    user.background_completed = True
                    context.user_data['collecting_background'] = False
                    context.user_data.pop('background_step', None)
                    await update.message.reply_text(
                        "Thanks for sharing! I'll use this to offer you even better support. "
                        "What's on your mind today? 🧐")

                db.commit()

            except Exception as e:
                print(f"[Error] Background collection failed: {str(e)}")
                await update.message.reply_text("An error occurred. Please try again.")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced message handler with improved error recovery and connection management"""
        logger.info("=== Starting new message handling ===")
        logger.info("Received message: %s from user: %s", 
            update.message.text[:50] if update.message else "No message",
            update.effective_user.id if update.effective_user else "No user"
        )
        
        # Enhanced validation with detailed logging
        if not update.effective_user:
            logger.error("Missing effective user in update")
            return
        if not update.message:
            logger.error("Missing message in update")
            return
        if not update.message.text:
            logger.error("Missing message text in update")
            return
            
        # Log complete message details for debugging
        logger.info("Message validation successful - "
                   f"Chat ID: {update.effective_chat.id}, "
                   f"User ID: {update.effective_user.id}, "
                   f"Message ID: {update.message.message_id}")

        user_id = update.effective_user.id
        message_text = update.message.text
        
        logger.info(f"Message details - Chat ID: {update.effective_chat.id}, User ID: {update.effective_user.id}, Message ID: {update.message.message_id}")
        logger.debug("Message content preview: %s...", message_text[:50])
        
        # Enhanced message flow logging
        logger.info("Starting message processing pipeline")

        try:
            # Check for {clearnow} command
            if message_text.strip() == "{clearnow}":
                logger.info("Clearnow command received from user %s", user_id)
                await self.clearnow_command(update, context)
                return

            async with db_session() as db:
                # Handle background collection if needed
                user = db.query(User).get(user_id)
                if not user:
                    user = User(
                        id=user_id,
                        username=update.effective_user.username,
                        first_name=update.effective_user.first_name,
                        joined_at=datetime.utcnow()
                    )
                    db.add(user)
                    db.commit()

                if not user.background_completed and not context.user_data.get('collecting_background', False):
                    context.user_data['collecting_background'] = True
                    context.user_data['background_step'] = 'age'
                    await update.message.reply_text(
                        "Before we continue, I'd like to learn a bit about you to provide better support.\n\n"
                        "What is your age? (Please enter a number)")
                    return

            if context.user_data.get('collecting_background', False):
                await self.handle_background_collection(update, context, user_id, message_text)
                return

            # Enhanced message processing with improved monitoring and retry logic
            retry_count = 5  # Increased retry attempts
            base_retry_delay = 1
            message_saved = False
            last_error = None
            
            for attempt in range(retry_count):
                try:
                    logger.info(f"Starting message processing (attempt {attempt + 1}/{retry_count})")
                    async with db_session() as db:
                        # Monitor database connection health
                        try:
                            await asyncio.wait_for(
                                asyncio.get_event_loop().run_in_executor(
                                    None,
                                    lambda: db.execute(text("SELECT 1")).scalar()
                                ),
                                timeout=5.0
                            )
                        except Exception as e:
                            logger.error(f"Database health check failed: {str(e)}")
                            raise
                        
                        # Optimistic locking with retry on conflict
                        try:
                            # Save message with transaction isolation
                            message = save_message(user_id, message_text, True)
                            logger.info(f"Message {message.id if message else 'None'} saved to database")
                            
                            # Update user activity with row-level locking
                            user = db.query(User).with_for_update(nowait=True).get(user_id)
                            if user:
                                user.last_activity = datetime.utcnow()
                                logger.info(f"User {user_id} activity timestamp updated")
                            
                            db.commit()
                            logger.info("Database transaction completed successfully")
                            message_saved = True
                            break
                            
                        except Exception as e:
                            db.rollback()
                            logger.error(f"Transaction error: {str(e)}")
                            raise
                            
                except asyncio.TimeoutError as e:
                    last_error = f"Database timeout (attempt {attempt + 1}/{retry_count})"
                    logger.error(last_error)
                except Exception as e:
                    last_error = f"Message processing error (attempt {attempt + 1}/{retry_count}): {str(e)}"
                    logger.error(last_error)
                
                if attempt < retry_count - 1:
                    # Exponential backoff with jitter
                    wait_time = min(base_retry_delay * (2 ** attempt) + random.uniform(0, 1), 30)
                    logger.info(f"Retrying in {wait_time:.2f} seconds...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"All message processing attempts failed: {last_error}")
            
            if not message_saved:
                logger.error("Failed to save message after all attempts")
                await update.message.reply_text(
                    "I'm having trouble processing your message. Please try again in a moment."
                )
                return
                
            logger.info("Message successfully saved and ready for processing")

            can_respond, remaining = increment_message_count(user_id)

            if not can_respond:
                async with db_session() as db:
                    user = db.query(User).get(user_id)
                    if user:
                        user.subscription_prompt_views += 1
                        db.commit()
                await update.message.reply_text(SUBSCRIPTION_PROMPT)
                return

            # Create typing indicator task
            typing_task = asyncio.create_task(self._keep_typing(update.effective_chat.id, context.bot))
            
            try:
                # Enhanced AI response handling with improved retry logic and error recovery
                response = theme = sentiment = None
                max_retries = 5  # Increased retry attempts
                base_delay = 2
                max_delay = 30
                last_error = None

                for attempt in range(max_retries):
                    try:
                        logger.info(f"Attempting to get AI response (attempt {attempt + 1}/{max_retries})")
                        
                        # Add timeout for the entire operation
                        async with asyncio.timeout(45.0):  # Increased timeout for the whole operation
                            response, theme, sentiment = await asyncio.wait_for(
                                asyncio.get_event_loop().run_in_executor(
                                    None, get_therapy_response, message_text, user_id
                                ),
                                timeout=30.0
                            )
                            
                        if response:
                            logger.info("AI response received successfully")
                            break
                            
                    except (asyncio.TimeoutError, TimedOut) as e:
                        last_error = f"Response generation timeout (attempt {attempt + 1}/{max_retries})"
                        logger.error(last_error)
                        
                    except NetworkError as e:
                        last_error = f"Network error (attempt {attempt + 1}/{max_retries}): {str(e)}"
                        logger.error(last_error)
                        
                    except Exception as e:
                        last_error = f"Unexpected error (attempt {attempt + 1}/{max_retries}): {str(e)}"
                        logger.error(last_error)
                    
                    if attempt < max_retries - 1:
                        # Exponential backoff with jitter
                        delay = min(base_delay * (2 ** attempt) + random.uniform(0, 1), max_delay)
                        logger.info(f"Retrying in {delay:.2f} seconds...")
                        await asyncio.sleep(delay)
                    else:
                        # Final attempt failed, send appropriate message
                        error_message = (
                            "I'm currently experiencing some technical difficulties. "
                            "Please try again in a few moments."
                        )
                        if isinstance(last_error, (asyncio.TimeoutError, TimedOut)):
                            error_message = (
                                "I'm taking longer than expected to process your message. "
                                "Please try again."
                            )
                        await update.message.reply_text(error_message)
                        return
                
                if not response:
                    return
                
                # Update message theme and sentiment
                async with db_session() as db:
                    latest_message = db.query(Message).filter(
                        Message.user_id == user_id
                    ).order_by(Message.created_at.desc()).first()
                    if latest_message:
                        latest_message.theme = theme
                        latest_message.sentiment_score = sentiment
                        db.commit()

                # Enhanced message saving and sending with proper error handling
                try:
                    # Save the response message
                    save_message(user_id, response, False)
                    logger.info("Bot response saved to database")
                except Exception as e:
                    logger.error(f"Failed to save bot response: {str(e)}")
                    # Continue with sending, but log the error
                
                # Improved message sending with retries
                send_retries = 3
                send_base_delay = 1
                for send_attempt in range(send_retries):
                    try:
                        logger.info(f"Attempting to send response (attempt {send_attempt + 1}/{send_retries})")
                        async with asyncio.timeout(10.0):
                            sent_message = await update.message.reply_text(response)
                            logger.info(f"Response successfully sent - Message ID: {sent_message.message_id}")
                            break
                            
                    except (TimedOut, NetworkError) as e:
                        logger.error(f"Network error sending message (attempt {send_attempt + 1}/{send_retries}): {str(e)}")
                        if send_attempt == send_retries - 1:
                            await update.message.reply_text(
                                "I'm having trouble sending my response. Please wait a moment and try again."
                            )
                            return
                            
                    except TelegramError as e:
                        logger.error(f"Telegram API error (attempt {send_attempt + 1}/{send_retries}): {str(e)}")
                        if send_attempt == send_retries - 1:
                            await update.message.reply_text(
                                "I encountered an error while sending my response. Please try again."
                            )
                            return
                            
                    if send_attempt < send_retries - 1:
                        delay = send_base_delay * (2 ** send_attempt)
                        await asyncio.sleep(delay)
            finally:
                # Ensure typing indicator is canceled
                typing_task.cancel()
                try:
                    await typing_task
                except asyncio.CancelledError:
                    pass

            # Notify about remaining messages
            if 0 < remaining <= 2:
                await update.message.reply_text(
                    f"⚠️ Only {remaining} messages left! "
                    "Upgrade now to unlock unlimited conversations!")

        except Exception as e:
            print(f"[Error] Message handling failed: {str(e)}")
            await update.message.reply_text(
                "I apologize, but I encountered an error processing your message. Please try again."
            )
        
        logger.info("=== Message handling completed ===")

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        print(f"[Error] Bot error: {context.error}")
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "I apologize, but I encountered an error. Please try again later."
            )

    async def _health_check(self):
        """Enhanced periodic health check to ensure bot responsiveness with proper recovery"""
        consecutive_failures = 0
        max_consecutive_failures = 3
        base_check_interval = 60  # Start with 1 minute
        max_check_interval = 300  # Max 5 minutes
        
        while True:
            try:
                # Comprehensive health check
                me = await asyncio.wait_for(self.application.bot.get_me(), timeout=10.0)
                if me and me.id:
                    logger.info(f"Bot health check: OK (ID: {me.id})")
                    consecutive_failures = 0  # Reset failure counter
                    await asyncio.sleep(base_check_interval)  # Normal interval if healthy
                    continue
                
                raise Exception("Invalid bot response")
                
            except asyncio.TimeoutError:
                logger.error("Bot health check timeout")
                consecutive_failures += 1
            except Exception as e:
                logger.error(f"Bot health check failed: {str(e)}")
                consecutive_failures += 1
            
            # Progressive recovery based on failure count
            if consecutive_failures >= max_consecutive_failures:
                logger.critical(f"Critical: {consecutive_failures} consecutive health check failures")
                try:
                    logger.info("Attempting full bot recovery")
                    await self.stop()
                    await asyncio.sleep(5)  # Wait for cleanup
                    self.__init__()
                    await self.initialize()
                    await self.application.start()
                    logger.info("Bot recovered successfully")
                    consecutive_failures = 0
                except Exception as recovery_error:
                    logger.error(f"Bot recovery failed: {str(recovery_error)}")
                    # Implement exponential backoff for recovery attempts
                    await asyncio.sleep(min(base_check_interval * (2 ** consecutive_failures), max_check_interval))
            else:
                # Implement exponential backoff for normal retries
                retry_interval = min(base_check_interval * (2 ** consecutive_failures), max_check_interval)
                logger.info(f"Waiting {retry_interval} seconds before next health check")
                await asyncio.sleep(retry_interval)

    async def initialize(self):
        """Initialize bot handlers with enhanced error handling and connection management"""
        try:
            # Configure handlers with proper order and rate limiting
            self.application.add_handler(CommandHandler("start", self.start_command, 
                                                      block=False))
            self.application.add_handler(CommandHandler("help", self.help_command,
                                                      block=False))
            self.application.add_handler(CommandHandler("subscribe", self.subscribe_command,
                                                      block=False))
            self.application.add_handler(CommandHandler("status", self.status_command,
                                                      block=False))
            self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,
                                                      self.handle_message,
                                                      block=False))
            self.application.add_error_handler(self.error_handler)
            
            # Add rate limiting middleware
            self.application.update_queue = asyncio.Queue(maxsize=100)  # Limit concurrent updates
            
            # Initialize the application
            await self.application.initialize()
            
            # Start health check task
            self._health_check_task = asyncio.create_task(self._health_check())
            logger.info("Bot successfully initialized")
        except Exception as e:
            logger.error(f"Bot initialization failed: {str(e)}")
            raise

    async def start(self):
        """Start the bot with polling"""
        try:
            await self.application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
                close_loop=False
            )
        except Exception as e:
            logger.error(f"Bot startup failed: {str(e)}")
            raise

    async def stop(self):
        """Stop the bot"""
        if self.application:
            await self.application.stop()
            await self.application.shutdown()

def create_bot_application():
    return BotApplication()