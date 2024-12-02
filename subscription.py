from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from database import get_db_session
from models import User, Message
from config import FREE_MESSAGE_LIMIT, WEEKLY_FREE_MESSAGES

def check_subscription_status(user_id: int) -> bool:
    """Check if user has an active subscription."""
    db = get_db_session()
    try:
        user = db.query(User).get(user_id)
        if not user:
            return False
        return user.is_subscribed and (
            not user.subscription_end or user.subscription_end > datetime.utcnow()
        )
    except Exception:
        return False
    finally:
        db.close()

def increment_message_count(user_id: int) -> tuple[bool, int]:
    """Increment message count and check if user can send more messages."""
    db = get_db_session()
    try:
        user = db.query(User).get(user_id)
        if not user:
            return False, 0

        # Reset weekly messages if a week has passed
        if datetime.utcnow() - user.last_message_reset > timedelta(days=7):
            user.weekly_messages_count = 0
            user.last_message_reset = datetime.utcnow()

        # If subscribed, allow unlimited messages
        if check_subscription_status(user_id):
            return True, float('inf')

        # Check message limits
        if user.messages_count >= FREE_MESSAGE_LIMIT or user.weekly_messages_count >= WEEKLY_FREE_MESSAGES:
            return False, 0

        # Increment message counts
        user.messages_count += 1
        user.weekly_messages_count += 1
        db.commit()

        remaining = min(
            FREE_MESSAGE_LIMIT - user.messages_count,
            WEEKLY_FREE_MESSAGES - user.weekly_messages_count
        )
        return True, remaining

    except Exception:
        db.rollback()
        return False, 0
    finally:
        db.close()

def save_message(user_id: int, content: str, is_from_user: bool, theme: str = None, sentiment_score: float = None) -> bool:
    """Save a message to the database."""
    db = get_db_session()
    try:
        message = Message(
            user_id=user_id,
            content=content,
            is_from_user=is_from_user,
            theme=theme,
            sentiment_score=sentiment_score,
            timestamp=datetime.utcnow()
        )
        db.add(message)
        db.commit()
        return True
    except Exception:
        db.rollback()
        return False
    finally:
        db.close()
