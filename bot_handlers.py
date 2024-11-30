from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
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
from subscription import create_subscription
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
        user = get_or_create_user(
            update.effective_user.id,
            update.effective_user.username,
            update.effective_user.first_name
        )
        await update.message.reply_text(WELCOME_MESSAGE)

    @staticmethod
    async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(HELP_MESSAGE)

    @staticmethod
    async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "To subscribe for unlimited access ($15/month), please visit: "
            "[Payment Link] (implementation needed)"
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
        
        # Save incoming message
        save_message(user_id, message_text, True)
        
        # Check message limits
        can_respond, remaining = increment_message_count(user_id)
        
        if not can_respond:
            await update.message.reply_text(SUBSCRIPTION_PROMPT)
            return
        
        # Get AI response
        response = get_therapy_response(message_text)
        
        # Save bot response
        save_message(user_id, response, False)
        
        # Send response
        await update.message.reply_text(response)
        
        # Notify about remaining messages if close to limit
        if 0 < remaining <= 5:
            await update.message.reply_text(
                f"You have {remaining} free messages remaining. "
                "Consider subscribing for unlimited access!"
            )

    @staticmethod
    async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        print(f"Error occurred: {context.error}")
        if update:
            await update.message.reply_text(
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
