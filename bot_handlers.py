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
        print("Initializing bot application...")
        self.application = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # Add update handler to log all updates
        self.application.add_handler(MessageHandler(filters.ALL, self.log_update), -1)
        
        # Add command handlers
        print("Registering command handlers...")
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("subscribe", self.subscribe_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        # Add error handler
        print("Registering error handler...")
        self.application.add_error_handler(self.error_handler)
        
        print("Bot application initialization completed")
        await self.application.initialize()

    @staticmethod
    async def log_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Log any update received from Telegram."""
        try:
            user_id = update.effective_user.id if update.effective_user else "Unknown"
            update_type = "Unknown"
            
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
                
            print(f"Received update - Type: {update_type}, User ID: {user_id}")
            
        except Exception as e:
            print(f"Error logging update: {str(e)}")
    
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
            print(f"[Message Handler] Processing message from user {user_id}")
            print(f"[Message Handler] Message content: {message_text[:50]}...")
            
            try:
                # Echo the message back immediately to confirm receipt
                await update.message.reply_text(
                    "Message received! Let me think about that...",
                    quote=True
                )
                print(f"[Message Handler] Sent acknowledgment to user {user_id}")
            except TelegramError as e:
                print(f"[Message Handler] Failed to send acknowledgment: {str(e)}")
            
            try:
                # Save incoming message
                save_message(user_id, message_text, True)
                print(f"[Message Handler] Saved incoming message for user {user_id}")
            except Exception as e:
                print(f"[Message Handler] Error saving message: {str(e)}")
                raise
            
            try:
                # Check message limits
                can_respond, remaining = increment_message_count(user_id)
                print(f"[Message Handler] Message limit check: can_respond={can_respond}, remaining={remaining}")
                
                if not can_respond:
                    print(f"[Message Handler] User {user_id} reached message limit")
                    user = get_or_create_user(user_id)
                    user.subscription_prompt_views += 1
                    db.session.commit()
                    await update.message.reply_text(SUBSCRIPTION_PROMPT)
                    return
            except Exception as e:
                print(f"[Message Handler] Error checking message limits: {str(e)}")
                raise
            
            try:
                print(f"[Message Handler] Requesting AI response for user {user_id}")
                # Get AI response
                response = get_therapy_response(message_text)
                print(f"[Message Handler] Received AI response: {response[:50]}...")
            except Exception as e:
                print(f"[Message Handler] Error getting AI response: {str(e)}")
                raise
            
            try:
                # Save bot response
                save_message(user_id, response, False)
                print(f"[Message Handler] Saved bot response for user {user_id}")
            except Exception as e:
                print(f"[Message Handler] Error saving bot response: {str(e)}")
                raise
            
            try:
                # Send response
                await update.message.reply_text(response)
                print(f"[Message Handler] Sent AI response to user {user_id}")
            except TelegramError as e:
                print(f"[Message Handler] Error sending response: {str(e)}")
                raise
            
            # Notify about remaining messages if close to limit
            if 0 < remaining <= 5:
                try:
                    print(f"[Message Handler] Sending remaining messages notification: {remaining} messages")
                    await update.message.reply_text(
                        f"You have {remaining} free messages remaining. "
                        "Consider subscribing for unlimited access!"
                    )
                except TelegramError as e:
                    print(f"[Message Handler] Error sending remaining messages notification: {str(e)}")
                
        except Exception as e:
            print(f"[Message Handler] Critical error processing message from user {user_id}:")
            print(f"[Message Handler] Error type: {type(e).__name__}")
            print(f"[Message Handler] Error details: {str(e)}")
            try:
                await update.message.reply_text(
                    "I apologize, but I encountered an error processing your message. Please try again."
                )
            except TelegramError as send_error:
                print(f"[Message Handler] Failed to send error message: {str(send_error)}")

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
