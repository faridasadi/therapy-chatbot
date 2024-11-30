from datetime import datetime, timedelta
from sqlalchemy import func
from db import get_db_session
from models import User, Message, UserTheme, Subscription
from config import WEEKLY_FREE_MESSAGES
from telegram import Bot
from typing import List, Dict, Tuple
import asyncio
import json

async def send_telegram_message(bot: Bot, user_id: int, message: str):
    """Helper function to send Telegram messages."""
    try:
        await bot.send_message(chat_id=user_id, text=message)
        return True
    except Exception as e:
        print(f"Error sending message to user {user_id}: {str(e)}")
        return False

async def notify_weekly_reset(bot: Bot):
    """Notify users about their weekly message quota reset."""
    db = get_db_session()
    try:
        # Find users whose weekly messages were reset
        users = db.query(User).filter(
            User.last_message_reset <= datetime.utcnow() - timedelta(days=7),
            User.is_subscribed == False
        ).all()

        for user in users:
            message = (
                f"🎉 Good news! Your weekly message quota has been reset.\n"
                f"You now have {WEEKLY_FREE_MESSAGES} free messages available this week.\n\n"
                "Want unlimited access? Consider subscribing!"
            )
            
            # Update reset timestamp before sending to prevent duplicate notifications
            user.last_message_reset = datetime.utcnow()
            user.weekly_messages_count = 0
            db.commit()
            
            await send_telegram_message(bot, user.id, message)

    finally:
        db.close()

async def re_engage_inactive_users(bot: Bot):
    """Send personalized re-engagement messages to inactive users."""
    db = get_db_session()
    try:
        # Find users inactive for more than 3 days but less than 30 days
        inactive_users = db.query(User).join(Message)\
            .filter(
                Message.timestamp <= datetime.utcnow() - timedelta(days=3),
                Message.timestamp > datetime.utcnow() - timedelta(days=30)
            )\
            .group_by(User.id)\
            .all()

        for user in inactive_users:
            # Get user's most discussed themes and average sentiment
            themes = db.query(UserTheme)\
                .filter(UserTheme.user_id == user.id)\
                .order_by(UserTheme.frequency.desc())\
                .limit(2)\
                .all()

            if not themes:
                continue

            # Personalize message based on user themes and sentiment
            theme_message = f"I noticed you've been interested in discussing {themes[0].theme}"
            if len(themes) > 1:
                theme_message += f" and {themes[1].theme}"
            
            message = (
                f"👋 Hello! I've missed our conversations.\n\n"
                f"{theme_message}. Would you like to continue our discussion?\n\n"
                "I'm here whenever you're ready to talk."
            )
            
            await send_telegram_message(bot, user.id, message)

    finally:
        db.close()

async def subscription_reminders(bot: Bot):
    """Send subscription reminders to active free users."""
    db = get_db_session()
    try:
        # Find active free users with high message counts
        active_users = db.query(User)\
            .filter(
                User.is_subscribed == False,
                User.messages_count >= 15,
                User.subscription_prompt_views < 5  # Limit reminder frequency
            ).all()

        for user in active_users:
            # Personalize subscription message based on usage
            message = (
                "📊 I've noticed you're getting great value from our conversations!\n\n"
                "Upgrade to unlimited access to:\n"
                "✨ Chat anytime without limits\n"
                "🎯 Get more personalized responses\n"
                "💫 Continue your therapy journey without interruption\n\n"
                "Ready to upgrade? Use /subscribe to get started!"
            )
            
            user.subscription_prompt_views += 1
            db.commit()
            
            await send_telegram_message(bot, user.id, message)

    finally:
        db.close()

async def run_re_engagement_system(bot: Bot):
    """Main function to run all re-engagement tasks."""
    while True:
        try:
            await notify_weekly_reset(bot)
            await re_engage_inactive_users(bot)
            await subscription_reminders(bot)
            
            # Wait for 6 hours before next check
            await asyncio.sleep(6 * 60 * 60)
            
        except Exception as e:
            print(f"Error in re-engagement system: {str(e)}")
            await asyncio.sleep(300)  # Wait 5 minutes on error
