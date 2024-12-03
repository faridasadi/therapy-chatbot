import os
import time
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackContext
)
from monitoring import pipeline_monitor, monitor_pipeline_stage
from database import get_db_session
from models import User, Base
from ai_service import get_therapy_response
from datetime import datetime, timedelta
from sqlalchemy import text, create_engine
from database import get_db_session, engine
import asyncio

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BotApplication:
    def __init__(self):
        """Initialize bot application"""
        logger.info("[Bot] Initializing bot application")
        self.token = os.environ.get('TELEGRAM_BOT_TOKEN')
        if not self.token:
            raise ValueError("TELEGRAM_BOT_TOKEN not found in environment variables")
        
        self.application = Application.builder().token(self.token).build()
        logger.info("Bot application created with token length: %d", len(self.token))

    @monitor_pipeline_stage("message_received")
    async def handle_message(self, update: Update, context: CallbackContext):
        """Handle incoming messages with enhanced flow monitoring and error handling"""
        start_time = time.time()
        user_id = None
        max_retries = 3
        retry_delay = 1
        pipeline_stages = []
        
        try:
            pipeline_stages.append("Extracting user info")
            user_id = update.effective_user.id
            username = update.effective_user.username
            first_name = update.effective_user.first_name
            
            logger.info("[Pipeline] Message received from user %s (username: %s)", user_id, username)
            pipeline_stages.append("User info extracted")
            
            for attempt in range(max_retries):
                try:
                    # Initialize database tables if they don't exist
                    Base.metadata.create_all(bind=engine)
                    
                    with get_db_session() as db:
                        # Verify database connection
                        db.execute(text("SELECT 1"))
                        
                        # Get or create user with proper locking and retry mechanism
                        user = db.query(User).with_for_update(skip_locked=True).get(user_id)
                        if not user:
                            user = User(
                                id=user_id,
                                username=username,
                                first_name=first_name,
                                joined_at=datetime.utcnow(),
                                messages_count=0,
                                weekly_messages_count=0,
                                last_message_reset=datetime.utcnow(),
                                is_subscribed=False,
                                subscription_end=None,
                                subscription_prompt_views=0,
                                interaction_style='balanced'
                            )
                            db.add(user)
                            db.commit()
                            db.refresh(user)
                            logger.info(f"[Pipeline] Created new user record for user {user_id}")
                            pipeline_stages.append("New user record created")
                    break  # If successful, break the retry loop
                    
                except Exception as db_error:
                    error_msg = f"Database operation failed (attempt {attempt + 1}/{max_retries}): {str(db_error)}"
                    logger.warning(f"[Pipeline] {error_msg}")
                    pipeline_stages.append(f"Database error: {error_msg}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay * (2 ** attempt))
                        continue
                    raise  # Re-raise the last exception if all retries failed
                else:
                    # Update user information if needed
                    if user.username != username or user.first_name != first_name:
                        user.username = username
                        user.first_name = first_name
                        db.commit()
                        logger.info(f"Updated user record for user {user_id}")
                    
                    # Update message count and check limits
                    if not user.is_subscribed:
                        # Reset weekly messages if needed
                        if datetime.utcnow() - user.last_message_reset > timedelta(days=7):
                            user.weekly_messages_count = 0
                            user.last_message_reset = datetime.utcnow()
                        user.weekly_messages_count += 1
                    user.messages_count += 1
                    db.commit()
                    logger.info(f"Updated message count for user {user_id}")
            
            # Log processing start
            logger.info(f"Processing message from user {user_id}")
            
            # Get response from AI service
            pipeline_stages.append("Starting AI response generation")
            response_start_time = time.time()
            response, theme, sentiment = await get_therapy_response(
                update.message.text,
                user_id
            )
            response_time = time.time() - response_start_time
            logger.info(f"[Pipeline] Generated response for user {user_id} in {response_time:.2f}s")
            pipeline_stages.append(f"AI response generated in {response_time:.2f}s")
            
            # Send response to user
            pipeline_stages.append("Sending response to user")
            await update.message.reply_text(response)
            logger.info(f"[Pipeline] Sent response to user {user_id}")
            pipeline_stages.append("Response sent successfully")
            
            # Log total processing time and pipeline summary
            total_time = time.time() - start_time
            logger.info(f"[Pipeline] Total processing time for user {user_id}: {total_time:.2f}s")
            logger.info(f"[Pipeline] Completed stages: {' -> '.join(pipeline_stages)}")
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"[Pipeline] Error handling message for user {user_id}: {error_msg}")
            logger.error(f"[Pipeline] Failed at stage: {pipeline_stages[-1] if pipeline_stages else 'initialization'}")
            
            try:
                await update.message.reply_text(
                    "I apologize, but I'm having trouble processing your message. "
                    "Please try again in a moment."
                )
            except Exception as reply_error:
                logger.error(f"Failed to send error message to user: {str(reply_error)}")

    async def start_command(self, update: Update, context: CallbackContext):
        """Handle /start command"""
        welcome_message = (
            "👋 Welcome to Therapyyy! I'm here to listen and support you.\n\n"
            "You can start chatting with me right away. I'll do my best to provide "
            "thoughtful responses and support.\n\n"
            "Type /help for more information about how I can assist you."
        )
        await update.message.reply_text(welcome_message)

    async def help_command(self, update: Update, context: CallbackContext):
        """Handle /help command"""
        help_text = (
            "🤗 Here's how I can help:\n\n"
            "- Chat with me about anything that's on your mind\n"
            "- Share your feelings and experiences\n"
            "- Get support and perspective\n\n"
            "Commands:\n"
            "/start - Start a conversation\n"
            "/help - Show this help message\n"
            "/subscribe - Get information about subscription\n"
            "/status - Check your usage status"
        )
        await update.message.reply_text(help_text)

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
        """Initialize bot handlers with enhanced monitoring and verification"""
        logger.info("[Pipeline] Starting bot handler initialization")
        
        try:
            # Create database tables without transaction
            Base.metadata.create_all(bind=engine)
            logger.info("[Pipeline] Database tables created/verified")
            
            # Initialize command handlers
            handlers = [
                ("start", self.start_command),
                ("help", self.help_command),
                ("subscribe", self.subscribe_command),
                ("status", self.status_command)
            ]
            
            # Register handlers
            for command, handler in handlers:
                self.application.add_handler(CommandHandler(command, handler))
                logger.info(f"[Pipeline] Registered /{command} command handler")
            
            # Register message handler
            message_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
            self.application.add_handler(message_handler)
            logger.info("[Pipeline] Registered message handler")
            
            # Register error handler
            self.application.add_error_handler(self.error_handler)
            logger.info("[Pipeline] Registered error handler")
            
            # Verify database connection in a separate operation
            try:
                with get_db_session() as db:
                    db.execute(text("SELECT 1"))
                    logger.info("[Pipeline] Database connection verified successfully")
            except Exception as db_error:
                logger.error(f"[Pipeline] Database verification failed: {str(db_error)}")
                raise
            
            # Initialize application
            await self.application.initialize()
            logger.info("[Pipeline] Bot application initialized")
            
            # Final verification
            handlers_count = len(self.application.handlers[0])
            logger.info(f"[Pipeline] Successfully registered {handlers_count} handlers")
            
            return True
            
        except Exception as e:
            logger.error(f"[Pipeline] Error during bot initialization: {str(e)}")
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
