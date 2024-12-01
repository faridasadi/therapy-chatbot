import os
from datetime import datetime
from telegram import Update
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from config import TELEGRAM_TOKEN as TELEGRAM_BOT_TOKEN, WELCOME_MESSAGE, HELP_MESSAGE, SUBSCRIPTION_PROMPT
from models import Message, User
from ai_service import get_therapy_response
from database import get_db_session, get_or_create_user
from subscription import check_subscription_status, increment_message_count, save_message
import asyncio
from contextlib import asynccontextmanager

@asynccontextmanager
async def db_session():
    """Context manager for database sessions"""
    session = get_db_session()
    try:
        yield session
    finally:
        session.close()

class BotApplication:
    def __init__(self):
        self.debug_mode = True
        print("[Bot] Initializing bot application")
        self.application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

        # Register handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("subscribe", self.subscribe_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.application.add_error_handler(self.error_handler)

    async def get_status_message(self, user_id: int) -> str:
        """Generate status message based on user subscription status"""
        if check_subscription_status(user_id):
            return "You have an active subscription with unlimited messages! 🌟"
        
        async with db_session() as db:
            user = db.query(User).get(user_id)
            if not user:
                return "Error retrieving user status"
            
            remaining = max(0, 20 - user.messages_count)
            weekly_remaining = max(0, 20 - user.weekly_messages_count)
            return f"""Your current status:
- Free messages remaining: {remaining}
- Weekly free messages remaining: {weekly_remaining}"""

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_user:
            return

        user_id = update.effective_user.id
        async with db_session() as db:
            try:
                user = get_or_create_user(user_id, update.effective_user.username, update.effective_user.first_name)
                user_record = db.query(User).get(user_id)
                
                if not user_record.background_completed:
                    welcome_text = (
                        f"{WELCOME_MESSAGE}\n\n"
                        "To provide you with the best possible support, I'd like to learn a bit about you. "
                        "Please answer a few quick questions:\n\n"
                        "What is your age? (Just enter a number)")
                    context.user_data['collecting_background'] = True
                    context.user_data['background_step'] = 'age'
                else:
                    welcome_text = (
                        f"{WELCOME_MESSAGE}\n\n"
                        "Welcome back! I remember our previous conversations and I'm here to support you."
                    )
                
                await update.message.reply_text(welcome_text)
            except Exception as e:
                print(f"[Error] Start command failed: {str(e)}")
                await update.message.reply_text("An error occurred. Please try again.")

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
        if not update.effective_user or not update.message or not update.message.text:
            return

        user_id = update.effective_user.id
        message_text = update.message.text

        try:
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

            # Handle background collection if needed
            user = get_or_create_user(user_id)
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

            # Process regular message
            save_message(user_id, message_text, True)
            can_respond, remaining = increment_message_count(user_id)

            if not can_respond:
                async with db_session() as db:
                    user = db.query(User).get(user_id)
                    if user:
                        user.subscription_prompt_views += 1
                        db.commit()
                await update.message.reply_text(SUBSCRIPTION_PROMPT)
                return

            # Get and send AI response
            response, theme, sentiment = get_therapy_response(message_text, user_id)
            
            # Update message theme and sentiment
            async with db_session() as db:
                latest_message = db.query(Message).filter(
                    Message.user_id == user_id
                ).order_by(Message.timestamp.desc()).first()
                if latest_message:
                    latest_message.theme = theme
                    latest_message.sentiment_score = sentiment
                    db.commit()

            save_message(user_id, response, False)
            await update.message.reply_text(response)

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

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        print(f"[Error] Bot error: {context.error}")
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "I apologize, but I encountered an error. Please try again later."
            )

    async def start(self):
        """Start the bot"""
        try:
            await self.application.run_polling()
        except Exception as e:
            print(f"[Error] Bot startup failed: {str(e)}")
            raise

    async def stop(self):
        """Stop the bot"""
        if self.application:
            await self.application.stop()
            await self.application.shutdown()

def create_bot_application():
    return BotApplication()