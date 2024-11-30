from telegram import Update, LabeledPrice
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    PreCheckoutQueryHandler,
    ContextTypes,
    filters
)
from telegram.error import TelegramError
from app import db
from config import (
    TELEGRAM_TOKEN,
    WELCOME_MESSAGE,
    SUBSCRIPTION_PROMPT,
    HELP_MESSAGE
)
from database import (
    get_or_create_user,
    save_message,
    increment_message_count,
    check_subscription_status
)
from ai_service import get_therapy_response
from subscription import create_subscription, generate_payment_invoice
import asyncio
from contextlib import asynccontextmanager

class BotApplication:
    def __init__(self):
        self.application = None
        
    async def initialize(self):
        self.application = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # Add handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("subscribe", self.subscribe_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        # Add error handler
        self.application.add_error_handler(self.error_handler)
        
        await self.application.initialize()
    
    @staticmethod
    async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            print(f"Start command received from user {update.effective_user.id}")
            user = get_or_create_user(
                update.effective_user.id,
                update.effective_user.username,
                update.effective_user.first_name
            )
            await update.message.reply_text(WELCOME_MESSAGE)
            print(f"Start command completed for user {update.effective_user.id}")
        except Exception as e:
            print(f"Error in start command: {e}")
            await update.message.reply_text("An error occurred. Please try again.")

    @staticmethod
    async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(HELP_MESSAGE)

    @staticmethod
    async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle subscription command and track analytics."""
        try:
            user_id = update.effective_user.id
            user = get_or_create_user(user_id)
            
            # Increment subscription prompt views
            user.subscription_prompt_views += 1
            db.session.commit()
            
            await update.message.reply_text(SUBSCRIPTION_PROMPT)
        except Exception as e:
            print(f"Error in subscribe command: {e}")
            await update.message.reply_text(
                "An unexpected error occurred. Please try again later."
            )

    @staticmethod
    async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    @staticmethod
    async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        message_text = update.message.text
        
        try:
            print(f"Handling message from user {user_id}: {message_text[:20]}...")
            
            # Save incoming message
            save_message(user_id, message_text, True)
            print(f"Saved incoming message for user {user_id}")
            
            # Check message limits
            can_respond, remaining = increment_message_count(user_id)
            print(f"Message limit check for user {user_id}: can_respond={can_respond}, remaining={remaining}")
            
            if not can_respond:
                print(f"User {user_id} reached message limit, showing subscription prompt")
                user = get_or_create_user(user_id)
                user.subscription_prompt_views += 1
                db.session.commit()
                await update.message.reply_text(SUBSCRIPTION_PROMPT)
                return
            
            print(f"Getting AI response for user {user_id}")
            # Get AI response
            response = get_therapy_response(message_text)
            
            # Save bot response
            save_message(user_id, response, False)
            print(f"Saved bot response for user {user_id}")
            
            # Send response
            await update.message.reply_text(response)
            print(f"Sent response to user {user_id}")
            
            # Notify about remaining messages if close to limit
            if 0 < remaining <= 5:
                print(f"Sending remaining messages notification to user {user_id}: {remaining} messages left")
                await update.message.reply_text(
                    f"You have {remaining} free messages remaining. "
                    "Consider subscribing for unlimited access!"
                )
                
        except Exception as e:
            print(f"Error handling message from user {user_id}: {str(e)}")
            # Don't let the error break the event loop
            await update.message.reply_text(
                "I apologize, but I encountered an error processing your message. Please try again."
            )

    @staticmethod
    async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        error_msg = f"Error occurred: {context.error}"
        print(f"ERROR: {error_msg}")
        print(f"Update: {update}")
        print(f"Error context: {context}")
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "I apologize, but I encountered an error. Please try again later."
            )

    async def start(self):
        await self.application.start()

    async def stop(self):
        if self.application:
            await self.application.stop()
            await self.application.shutdown()

def create_bot_application():
    return BotApplication()
