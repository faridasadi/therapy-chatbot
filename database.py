from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import QueuePool
from contextlib import contextmanager
import os
from datetime import datetime, timedelta
from models import User, Message, UserTheme, Subscription
from typing import Optional
from config import FREE_MESSAGE_LIMIT, WEEKLY_FREE_MESSAGES

# Create engine with connection pooling
engine = create_engine(
    os.getenv('DATABASE_URL'),
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=1800
)

# Create session factory
SessionFactory = sessionmaker(bind=engine)
ScopedSession = scoped_session(SessionFactory)

@contextmanager
def get_db_session():
    """Context manager for database sessions"""
    session = ScopedSession()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        ScopedSession.remove()

def get_or_create_user(user_id: int, username: Optional[str] = None, first_name: Optional[str] = None) -> User:
    """Get or create a user with optimized session handling"""
    with get_db_session() as db:
        user = db.query(User).get(user_id)
        if not user:
            user = User(
                id=user_id,
                username=username,
                first_name=first_name,
                joined_at=datetime.utcnow()
            )
            db.add(user)
            db.commit()
        return user

def save_message(user_id: int, content: str, is_from_user: bool) -> Message:
    print(f"[Database] Attempting to save message for user {user_id}")
    with get_db_session() as db:
        try:
            message = Message(
                user_id=user_id,
                content=content,
                is_from_user=is_from_user
            )
            print(f"[Database] Message object created, length: {len(content)} chars")

            db.add(message)
            print(f"[Database] Message added to session")

            db.commit()
            db.refresh(message)
            print(f"[Database] Message successfully saved with ID: {message.id}")
            return message
        except Exception as e:
            print(f"[Database] Error saving message: {str(e)}")
            db.rollback()
            raise

def increment_message_count(user_id: int) -> tuple[bool, int]:
    print(f"[Database] Checking message count for user {user_id}")
    with get_db_session() as db:
        try:
            user = db.query(User).get(user_id)
            if not user:
                print(f"[Database] User {user_id} not found")
                return False, 0

            # Reset weekly messages if needed
            if datetime.utcnow() - user.last_message_reset > timedelta(days=7):
                user.weekly_messages_count = 0
                user.last_message_reset = datetime.utcnow()

            user.messages_count += 1
            user.weekly_messages_count += 1
            db.commit()

            if user.is_subscribed:
                return True, -1

            remaining = FREE_MESSAGE_LIMIT - user.messages_count
            if remaining < 0 and user.weekly_messages_count > WEEKLY_FREE_MESSAGES:
                return False, 0

            return True, remaining
        except Exception as e:
            print(f"[Database] Error incrementing message count: {str(e)}")
            db.rollback()
            raise

def check_subscription_status(user_id: int) -> bool:
    with get_db_session() as db:
        try:
            user = db.query(User).get(user_id)
            if not user:
                return False

            if not user.is_subscribed:
                return False

            if user.subscription_end and user.subscription_end < datetime.utcnow():
                user.is_subscribed = False
                db.commit()
                return False

            return True
        except Exception as e:
            print(f"[Database] Error checking subscription status: {str(e)}")
            db.rollback()
            raise


def clean_user_data(user_id: int) -> bool:
    """Clean up all user data and reset background information."""
    print(f"[Database] Starting data cleanup for user {user_id}")

    with get_db_session() as db:
        try:
            with db.begin():
                user = db.query(User).get(user_id)
                if not user:
                    print(f"[Database] User {user_id} not found")
                    return False

                # Use bulk delete for better performance
                db.query(Message).filter(Message.user_id == user_id).delete()
                db.query(UserTheme).filter(UserTheme.user_id == user_id).delete()
                db.query(Subscription).filter(Subscription.user_id == user_id).delete()

                # Reset user background information
                user.background_completed = False
                user.age = None
                user.gender = None
                user.therapy_experience = None
                user.primary_concerns = None
                user.messages_count = 0
                user.weekly_messages_count = 0
                user.last_message_reset = datetime.utcnow()

                print(f"[Database] Successfully cleaned up data for user {user_id}")
                return True

        except Exception as e:
            print(f"[Database] Error cleaning up user data: {str(e)}")
            return False