from datetime import datetime, timedelta
from sqlalchemy import func, and_, not_, text
from sqlalchemy.orm import immediateload
from database import get_db_session
from models import User, Message, UserTheme, Subscription
from config import WEEKLY_FREE_MESSAGES
from telegram import Bot
from telegram.error import TelegramError, TimedOut, NetworkError
from typing import List, Dict, Tuple
import asyncio
import json
import logging
import random
from time import time

# Configure logging
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
logger.addHandler(console_handler)

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
    """Enhanced helper function for sending Telegram messages with improved error handling."""
    max_retries = 3
    base_delay = 1
    last_error = None
    
    for attempt in range(max_retries):
        try:
            if not await check_rate_limit():
                logger.warning(f"Rate limit exceeded, delaying message to user {user_id}")
                await asyncio.sleep(60)
            
            logger.info(f"Attempting to send message to user {user_id} (attempt {attempt + 1}/{max_retries})")
            
            async with asyncio.timeout(10.0):
                await bot.send_message(chat_id=user_id, text=message)
                logger.info(f"Successfully sent message to user {user_id}")
                return True
                
        except asyncio.TimeoutError as e:
            last_error = f"Timeout sending message (attempt {attempt + 1}/{max_retries})"
            logger.error(last_error)
            
        except (TimedOut, NetworkError) as e:
            last_error = f"Network error (attempt {attempt + 1}/{max_retries}): {str(e)}"
            logger.error(last_error)
            
        except TelegramError as e:
            last_error = f"Telegram API error (attempt {attempt + 1}/{max_retries}): {str(e)}"
            logger.error(last_error)
            
        except Exception as e:
            last_error = f"Unexpected error (attempt {attempt + 1}/{max_retries}): {str(e)}"
            logger.error(last_error)
        
        if attempt < max_retries - 1:
            # Exponential backoff with jitter
            delay = min(base_delay * (2 ** attempt) + random.uniform(0, 1), 30)
            logger.info(f"Retrying in {delay:.2f} seconds...")
            await asyncio.sleep(delay)
            
    logger.error(f"Failed to send message after {max_retries} attempts: {last_error}")
    return False

async def notify_weekly_reset(bot: Bot):
    """Notify users about their weekly message quota reset."""
    logger.info("Starting weekly reset notification process")
    with get_db_session() as db:
        try:
            # Optimized query with proper indexing
            users = (
                db.query(User)
                .filter(
                    and_(
                        User.last_message_reset <= datetime.utcnow() - timedelta(days=7),
                        User.is_subscribed == False,
                        User.weekly_messages_count > 0
                    )
                )
                .with_for_update(skip_locked=True)
                .all()
            )
            
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
            raise

async def re_engage_inactive_users(bot: Bot):
    """Send personalized re-engagement messages to inactive users."""
    logger.info("Starting inactive users re-engagement process")
    with get_db_session() as db:
        try:
            three_days_ago = datetime.utcnow() - timedelta(days=3)
            thirty_days_ago = datetime.utcnow() - timedelta(days=30)
            
            # First get the latest message timestamps for each user
            latest_messages = (
                db.query(
                    Message.user_id,
                    func.max(Message.created_at).label('last_message')
                )
                .group_by(Message.user_id)
                .having(
                    and_(
                        func.max(Message.created_at) <= three_days_ago,
                        func.max(Message.created_at) > thirty_days_ago
                    )
                )
                .subquery()
            )
            
            # Then get the users with a separate FOR UPDATE query
            inactive_user_ids = [row[0] for row in db.query(latest_messages.c.user_id).all()]
            
            if not inactive_user_ids:
                logger.info("No inactive users found")
                return
            
            # Get users with locking in batches
            batch_size = 50
            inactive_users = []
            
            for i in range(0, len(inactive_user_ids), batch_size):
                batch_ids = inactive_user_ids[i:i + batch_size]
                batch_users = (
                    db.query(User)
                    .filter(User.id.in_(batch_ids))
                    .with_for_update(skip_locked=True)
                    .options(immediateload(User.themes))
                    .all()
                )
                inactive_users.extend(batch_users)
                
            logger.info(f"Found {len(inactive_users)} inactive users to re-engage")
            
            success_count = 0
            for user in inactive_users:
                logger.info(f"Processing re-engagement for user {user.id}")
                
                # Optimized theme query with limit
                themes = (
                    db.query(UserTheme)
                    .filter(UserTheme.user_id == user.id)
                    .order_by(UserTheme.frequency.desc())
                    .limit(2)
                    .all()
                )

                if not themes:
                    logger.info(f"No themes found for user {user.id}, skipping")
                    continue

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
            raise

async def subscription_reminders(bot: Bot):
    """Send subscription reminders to active free users."""
    logger.info("Starting subscription reminder process")
    max_retries = 3
    base_delay = 1
    last_error = None

    for attempt in range(max_retries):
        try:
            with get_db_session() as db:
                # Verify database connection
                db.execute(text("SELECT 1")).scalar()
                
                # Optimized query with proper filtering
                active_users = (
                    db.query(User)
                    .filter(
                        and_(
                            User.is_subscribed == False,
                            User.messages_count >= 15,
                            User.subscription_prompt_views < 5
                        )
                    )
                    .with_for_update(skip_locked=True)
                    .all()
                )
                
                if active_users is not None:  # Successful query
                    break
                    
        except Exception as e:
            last_error = f"Database error (attempt {attempt + 1}/{max_retries}): {str(e)}"
            logger.error(last_error)
            
            if attempt < max_retries - 1:
                delay = min(base_delay * (2 ** attempt) + random.uniform(0, 1), 30)
                logger.info(f"Retrying database connection in {delay:.2f} seconds...")
                await asyncio.sleep(delay)
            else:
                logger.error(f"All database connection attempts failed: {last_error}")
                return  # Skip this cycle if all retries fail
                
    try:
        logger.info(f"Found {len(active_users)} users eligible for subscription reminders")
        
        success_count = 0
        failed_users = []
        
        for user in active_users:
            logger.info(f"Processing subscription reminder for user {user.id}")
            message = (
                "📊 I've noticed you're getting great value from our conversations!\n\n"
                "Upgrade to unlimited access to:\n"
                "✨ Chat anytime without limits\n"
                "🎯 Get more personalized responses\n"
                "💫 Continue your therapy journey without interruption\n\n"
                "Ready to upgrade? Use /subscribe to get started!"
            )
            
            try:
                with get_db_session() as db:
                    # Verify user still exists and lock row
                    current_user = db.query(User).filter(User.id == user.id).with_for_update(nowait=True).first()
                    if current_user:
                        current_user.subscription_prompt_views += 1
                        db.commit()
                        
                        if await send_telegram_message(bot, user.id, message):
                            success_count += 1
                        else:
                            failed_users.append(user.id)
                    else:
                        logger.warning(f"User {user.id} no longer exists")
                        
            except Exception as user_error:
                logger.error(f"Error processing user {user.id}: {str(user_error)}")
                failed_users.append(user.id)
                continue
                
        logger.info(f"Subscription reminders completed. Success: {success_count}/{len(active_users)}")
        if failed_users:
            logger.warning(f"Failed to process users: {failed_users}")

    except Exception as e:
        logger.error(f"Error in subscription_reminders: {str(e)}")
        raise

async def run_re_engagement_system(bot: Bot):
    """Main function to run all re-engagement tasks with enhanced error handling."""
    logger.info("Starting re-engagement system")
    
    while True:
        try:
            logger.info("Beginning re-engagement cycle")
            
            # Execute re-engagement tasks with proper delays and monitoring
            try:
                logger.info("Starting weekly reset notifications")
                await notify_weekly_reset(bot)
                logger.info("Weekly reset notifications completed")
            except Exception as e:
                logger.error(f"Error in weekly reset task: {str(e)}")
            
            await asyncio.sleep(60)  # Rate limiting between tasks
            
            try:
                logger.info("Starting inactive users re-engagement")
                await re_engage_inactive_users(bot)
                logger.info("Inactive users re-engagement completed")
            except Exception as e:
                logger.error(f"Error in inactive users task: {str(e)}")
            
            await asyncio.sleep(60)  # Rate limiting between tasks
            
            try:
                logger.info("Starting subscription reminders")
                await subscription_reminders(bot)
                logger.info("Subscription reminders completed")
            except Exception as e:
                logger.error(f"Error in subscription reminders task: {str(e)}")
            
            logger.info("Re-engagement cycle completed")
            
            # Wait for 6 hours before next check
            logger.info("Waiting 6 hours before next cycle")
            await asyncio.sleep(6 * 60 * 60)
            
        except asyncio.CancelledError:
            logger.info("Re-engagement system shutdown requested")
            break
        except Exception as e:
            logger.error(f"Critical error in re-engagement system: {str(e)}")
            logger.info("Waiting 5 minutes before retry")
            await asyncio.sleep(300)  # Wait 5 minutes on error
            continue
