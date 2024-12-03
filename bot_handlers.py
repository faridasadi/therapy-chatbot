import os
import time
import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
from telegram import Update
from telegram.constants import ChatAction, ChatType
from monitoring import pipeline_monitor, monitor_pipeline_stage
from database import get_db_session
from models import User
from ai_service import get_therapy_response
import asyncio

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BotApplication:

    def __init__(self):
        """Initialize bot application with enhanced error handling"""
        logger.info("[Bot] Initializing bot application")
        try:
            self.token = os.environ.get('TELEGRAM_BOT_TOKEN')
            if not self.token or not self.token.strip():
                raise ValueError("TELEGRAM_BOT_TOKEN not found in environment variables or is empty")
            
            # Create the application with the token directly
            self.application = Application.builder().token(self.token).build()
            logger.info("Bot application created successfully")
            
        except ValueError as ve:
            logger.error(f"Token validation error: {str(ve)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during bot initialization: {str(e)}")
            raise ValueError(f"Failed to initialize bot: {str(e)}")

    @monitor_pipeline_stage("message_received")
    async def handle_message(self, update: Update, context: CallbackContext):
        """Handle incoming messages with basic flow monitoring"""
        start_time = time.time()
        try:
            user_id = update.effective_user.id
            logger.info("Message received from user %s", user_id)

            # Record processing start
            process_start_time = time.time()
            pipeline_monitor.record_pipeline_stage(
                "processing_start", process_start_time - start_time)
            logger.info("Message processing started for user %s", user_id)

            # Get response from AI service
            response_start_time = time.time()
            response, theme, sentiment = await get_therapy_response(
                update.message.text, user_id)

            # Record response generation
            response_time = time.time() - response_start_time
            pipeline_monitor.record_pipeline_stage("response_generated",
                                                   response_time)
            logger.info("Response generated in %.2fs", response_time)

            # Send response back to user
            send_start_time = time.time()
            await update.message.reply_text(response)

            # Record message sent
            send_time = time.time() - send_start_time
            pipeline_monitor.record_pipeline_stage("response_sent", send_time)
            logger.info("Response sent to user %s in %.2fs", user_id,
                        send_time)

            # Record total processing time
            total_time = time.time() - start_time
            logger.info("Total processing time for user %s: %.2fs", user_id,
                        total_time)

        except Exception as e:
            logger.error(f"Error handling message: {str(e)}")
            await update.message.reply_text(
                "I apologize, but I'm having trouble processing your message. Could you try again?"
            )

    async def start_command(self, update: Update, context: CallbackContext):
        """Handle /start command"""
        welcome_message = (
            "👋 Welcome to Therapyyy! I'm here to listen and support you.\n\n"
            "You can start chatting with me right away. I'll do my best to provide "
            "thoughtful responses and support.\n\n"
            "Type /help for more information about how I can assist you.")
        await update.message.reply_text(welcome_message)

    async def help_command(self, update: Update, context: CallbackContext):
        """Handle /help command"""
        help_text = ("🤗 Here's how I can help:\n\n"
                     "- Chat with me about anything that's on your mind\n"
                     "- Share your feelings and experiences\n"
                     "- Get support and perspective\n\n"
                     "Commands:\n"
                     "/start - Start a conversation\n"
                     "/help - Show this help message\n"
                     "/subscribe - Get information about subscription\n"
                     "/status - Check your usage status")
        await update.message.reply_text(help_text)

    async def subscribe_command(self, update: Update,
                                context: CallbackContext):
        """Handle /subscribe command"""
        subscription_text = (
            "💎 Premium Features:\n\n"
            "- Unlimited conversations\n"
            "- Priority response time\n"
            "- Enhanced conversation memory\n\n"
            "Contact our support team for subscription details.")
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
            else:
                status = "Sorry, I couldn't find your user information."
        await update.message.reply_text(status)

    async def error_handler(self, update: object, context: CallbackContext):
        """Handle errors"""
        logger.error(f"Error handling update: {context.error}")

    async def initialize(self):
        """Initialize bot handlers"""
        try:
            # Configure handlers
            self.application.add_handler(
                CommandHandler("start", self.start_command, block=False))
            self.application.add_handler(
                CommandHandler("help", self.help_command, block=False))
            self.application.add_handler(
                CommandHandler("subscribe",
                               self.subscribe_command,
                               block=False))
            self.application.add_handler(
                CommandHandler("status", self.status_command, block=False))
            self.application.add_handler(
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                               self.handle_message,
                               block=False))
            self.application.add_error_handler(self.error_handler)

            await self.application.initialize()
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
                close_loop=False)
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
