import os
from datetime import datetime
from telegram import Update
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from config import TELEGRAM_TOKEN as TELEGRAM_BOT_TOKEN, WELCOME_MESSAGE, HELP_MESSAGE, SUBSCRIPTION_PROMPT #Corrected import and renamed TELEGRAM_TOKEN
from models import Message, User
from ai_service import get_therapy_response
from database import get_db_session, get_or_create_user
from subscription import check_subscription_status, increment_message_count, save_message #Corrected import
import asyncio
from contextlib import asynccontextmanager

class BotApplication:
    def __init__(self):
        self.debug_mode = True  # Initialize debug_mode first
        self.debug_print("Initializing bot application")
        self.application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        
        # Register handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command)) #Restored help command handler
        self.application.add_handler(CommandHandler("subscribe", self.subscribe_command)) #Restored subscribe command handler
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.application.add_handler(MessageHandler(filters.ALL, self.log_update), -1) #Restored update logger
        self.application.add_error_handler(self.error_handler)
        self.debug_mode = True
        
    def debug_print(self, message: str):
        """Print debug messages with timestamp"""
        if self.debug_mode:
            timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
            print(f"[Debug {timestamp}] {message}")

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
            
            db = get_db_session()
            try:
                user_record = db.query(User).get(update.effective_user.id)
                if not user_record.background_completed:
                    welcome_text = (
                        f"{WELCOME_MESSAGE}\n\n"
                        "To provide you with the best possible support, I'd like to learn a bit about you. "
                        "Please answer a few quick questions:\n\n"
                        "What is your age? (Just enter a number)"
                    )
                    context.user_data['collecting_background'] = True
                    context.user_data['background_step'] = 'age'
                else:
                    welcome_text = (
                        f"{WELCOME_MESSAGE}\n\n"
                        "Welcome back! I remember our previous conversations and I'm here to support you."
                    )
            finally:
                db.close()
                
            await update.message.reply_text(welcome_text)
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

    async def handle_background_collection(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, message_text: str):
        self.debug_print(f"Processing background collection for user {user_id}")
        db = get_db_session()
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
                            "- Non-binary\n"
                            "- Prefer not to say"
                        )
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
                        "- Had therapy in the past"
                    )
                else:
                    await update.message.reply_text("Please select one of the provided options.")
                    
            elif current_step == 'therapy_experience':
                valid_experiences = ['never', 'currently in therapy', 'had therapy in the past']
                if message_text.lower() in valid_experiences:
                    user.therapy_experience = message_text.lower()
                    context.user_data['background_step'] = 'primary_concerns'
                    await update.message.reply_text(
                        "Last question: What are your primary concerns or reasons for seeking support? "
                        "Please briefly describe them."
                    )
                else:
                    await update.message.reply_text("Please select one of the provided options.")
                    
            elif current_step == 'primary_concerns':
                user.primary_concerns = message_text
                user.background_completed = True
                context.user_data['collecting_background'] = False
                context.user_data.pop('background_step', None)
                
                await update.message.reply_text(
                    "Thanks for sharing! I'll use this to offer you even better support. "
                    "What's on your mind today? 🧐"
                )
                
            db.commit()
            
        except Exception as e:
            self.debug_print(f"Error in background collection: {str(e)}")
            await update.message.reply_text("An error occurred. Please try again.")
        finally:
            db.close()

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

            # Test database connection and check background collection status
            try:
                user = get_or_create_user(user_id)
                self.debug_print(f"Database connection verified - User found/created")
                
                # Check if we need to start background collection
                if not user.background_completed and not context.user_data.get('collecting_background', False):
                    self.debug_print(f"Initiating background collection for user {user_id}")
                    context.user_data['collecting_background'] = True
                    context.user_data['background_step'] = 'age'
                    await update.message.reply_text(
                        "Before we continue, I'd like to learn a bit about you to provide better support.\n\n"
                        "What is your age? (Please enter a number)"
                    )
                    return
                
                # Handle ongoing background information collection
                if context.user_data.get('collecting_background', False):
                    await self.handle_background_collection(update, context, user_id, message_text)
                    return
                    
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
            self.debug_print(f"Critical error processing message:")
            self.debug_print(f"Error type: {type(e).__name__}")
            self.debug_print(f"Error details: {str(e)}")
            try:
                await update.message.reply_text(
                    "I apologize, but I encountered an error processing your message. Please try again."
                )
            except TelegramError as send_error:
                self.debug_print(f"Failed to send error message: {str(send_error)}")

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.debug_print(f"Error occurred: {context.error}")
        self.debug_print(f"Update: {update}")
        self.debug_print(f"Error context: {context}")
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "I apologize, but I encountered an error. Please try again later."
            )

    async def start(self):
        """Start the bot"""
        self.debug_print("Starting bot...")
        try:
            await self.application.run_polling() #corrected start method
            self.debug_print("Bot started successfully!")
        except Exception as e:
            self.debug_print(f"Error starting bot: {str(e)}")
            raise

    async def stop(self):
        """Stop the bot"""
        if self.application:
            self.debug_print("Stopping bot...")
            await self.application.stop()
            await self.application.shutdown()
            self.debug_print("Bot stopped successfully")

def create_bot_application():
    return BotApplication()