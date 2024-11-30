from datetime import datetime, timedelta
from sqlalchemy import func
from db import get_db_session
from models import User, Message, UserTheme, Subscription
from config import WEEKLY_FREE_MESSAGES
from telegram import Bot
from telegram.error import TelegramError
from typing import List, Dict, Tuple
import asyncio
import json
import logging
from time import time

# Configure logging
import os
from logging.handlers import RotatingFileHandler

# Ensure logs directory exists
os.makedirs('static/logs', exist_ok=True)

# Configure logging with both file and console handlers
logger = logging.getLogger('re_engagement')
logger.setLevel(logging.INFO)

# Console handler with detailed formatting
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_format = logging.Formatter(
    '\033[92m%(asctime)s\033[0m - \033[94m%(name)s\033[0m - \033[93m%(levelname)s\033[0m - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
console_handler.setFormatter(console_format)

# File handler with rotation
file_handler = RotatingFileHandler(
    'static/logs/re_engagement.log',
    maxBytes=1024*1024,  # 1MB
    backupCount=5
)
file_handler.setLevel(logging.INFO)
file_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_format)

# Add handlers to logger
logger.addHandler(console_handler)
logger.addHandler(file_handler)

# Rate limiting configuration
RATE_LIMIT = {
    'messages_per_minute': 30,
    'last_reset': time(),
    'message_count': 0
}

async def check_rate_limit() -> bool:
    """Check if we're within rate limits."""
    current_time = time()
    if current_time - RATE_LIMIT['last_reset'] >= 60:
        RATE_LIMIT['last_reset'] = current_time
        RATE_LIMIT['message_count'] = 0
        return True
    
    if RATE_LIMIT['message_count'] >= RATE_LIMIT['messages_per_minute']:
        return False
    
    RATE_LIMIT['message_count'] += 1
    return True

async def send_telegram_message(bot: Bot, user_id: int, message: str) -> bool:
    """Helper function to send Telegram messages with rate limiting."""
    try:
        if not await check_rate_limit():
            logger.warning(f"Rate limit exceeded, delaying message to user {user_id}")
            await asyncio.sleep(60)
            
        logger.info(f"Attempting to send message to user {user_id}")
        await bot.send_message(chat_id=user_id, text=message)
        logger.info(f"Successfully sent message to user {user_id}")
        return True
        
    except TelegramError as e:
        error_id = error_logger.log_error(
            error=e,
            component='telegram_message',
            severity='WARNING',
            context={'user_id': user_id, 'action': 'send_message'}
        )
        logger.error(f"Telegram error sending message to user {user_id} (Error ID: {error_id})")
        return False
    except Exception as e:
        error_id = error_logger.log_error(
            error=e,
            component='telegram_message',
            severity='ERROR',
            context={'user_id': user_id, 'action': 'send_message'}
        )
        logger.error(f"Unexpected error sending message to user {user_id} (Error ID: {error_id})")
        return False

async def notify_weekly_reset(bot: Bot):
    """Notify users about their weekly message quota reset."""
    logger.info("Starting weekly reset notification process")
    db = get_db_session()
    try:
        # Find users whose weekly messages were reset
        users = db.query(User).filter(
            User.last_message_reset <= datetime.utcnow() - timedelta(days=7),
            User.is_subscribed == False
        ).all()
        
        logger.info(f"Found {len(users)} users eligible for weekly reset notification")
        
        success_count = 0
        for user in users:
            logger.info(f"Processing weekly reset for user {user.id}")
            message = (
                f"🎉 Good news! Your weekly message quota has been reset.\n"
                f"You now have {WEEKLY_FREE_MESSAGES} free messages available this week.\n\n"
                "Want unlimited access? Consider subscribing!"
            )
            
            # Update reset timestamp before sending to prevent duplicate notifications
            user.last_message_reset = datetime.utcnow()
            user.weekly_messages_count = 0
            db.commit()
            
            if await send_telegram_message(bot, user.id, message):
                success_count += 1
                
        logger.info(f"Weekly reset notifications completed. Success: {success_count}/{len(users)}")

    except Exception as e:
        logger.error(f"Error in notify_weekly_reset: {str(e)}")
        db.rollback()
    finally:
        db.close()

async def re_engage_inactive_users(bot: Bot):
    """Send personalized re-engagement messages to inactive users."""
    logger.info("Starting inactive users re-engagement process")
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
            
        logger.info(f"Found {len(inactive_users)} inactive users to re-engage")
        
        success_count = 0
        for user in inactive_users:
            logger.info(f"Processing re-engagement for user {user.id}")
            # Get user's most discussed themes and average sentiment
            themes = db.query(UserTheme)\
                .filter(UserTheme.user_id == user.id)\
                .order_by(UserTheme.frequency.desc())\
                .limit(2)\
                .all()

            if not themes:
                logger.info(f"No themes found for user {user.id}, skipping")
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
            
            if await send_telegram_message(bot, user.id, message):
                success_count += 1
                
        logger.info(f"Inactive user re-engagement completed. Success: {success_count}/{len(inactive_users)}")

    except Exception as e:
        logger.error(f"Error in re_engage_inactive_users: {str(e)}")
        db.rollback()
    finally:
        db.close()

async def subscription_reminders(bot: Bot):
    """Send subscription reminders to active free users."""
    logger.info("Starting subscription reminder process")
    db = get_db_session()
    try:
        # Find active free users with high message counts
        active_users = db.query(User)\
            .filter(
                User.is_subscribed == False,
                User.messages_count >= 15,
                User.subscription_prompt_views < 5  # Limit reminder frequency
            ).all()
            
        logger.info(f"Found {len(active_users)} users eligible for subscription reminders")
        
        success_count = 0
        for user in active_users:
            logger.info(f"Processing subscription reminder for user {user.id}")
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
            
            if await send_telegram_message(bot, user.id, message):
                success_count += 1
                
        logger.info(f"Subscription reminders completed. Success: {success_count}/{len(active_users)}")

    except Exception as e:
        logger.error(f"Error in subscription_reminders: {str(e)}")
        db.rollback()
    finally:
        db.close()

async def run_re_engagement_system(bot: Bot):
    """Main function to run all re-engagement tasks."""
    logger.info("Starting re-engagement system")
    
    while True:
        try:
            logger.info("Beginning re-engagement cycle")
            
            # Execute re-engagement tasks
            await notify_weekly_reset(bot)
            await asyncio.sleep(60)  # Rate limiting between tasks
            
            await re_engage_inactive_users(bot)
            await asyncio.sleep(60)  # Rate limiting between tasks
            
            await subscription_reminders(bot)
            
            logger.info("Re-engagement cycle completed successfully")
            
            # Wait for 6 hours before next check
            logger.info("Waiting 6 hours before next cycle")
            await asyncio.sleep(6 * 60 * 60)
            
        except Exception as e:
            # Use centralized error handling
            error_id = error_logger.log_error(
                error=e,
                component='re_engagement',
                severity='ERROR',
                context={
                    'stage': 'main_loop',
                    'last_action': 'run_re_engagement_system',
                    'error_count': RATE_LIMIT.get('error_count', 0)
                }
            )
            logger.error(f"Re-engagement system error (Error ID: {error_id})")
            
            # Implement exponential backoff
            retry_delay = min(300 * (2 ** RATE_LIMIT.get('error_count', 0)), 3600)
            RATE_LIMIT['error_count'] = RATE_LIMIT.get('error_count', 0) + 1
            
            logger.info(f"Waiting {retry_delay} seconds before retry (attempt {RATE_LIMIT['error_count']})")
            await asyncio.sleep(retry_delay)
            
            # Reset error count after successful execution
            if RATE_LIMIT['error_count'] >= 5:
                logger.error("Too many consecutive errors, entering recovery mode")
                RATE_LIMIT['error_count'] = 0
                await asyncio.sleep(3600)  # Wait 1 hour before resuming
