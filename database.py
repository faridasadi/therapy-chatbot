from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import QueuePool
from contextlib import contextmanager
import os
from datetime import datetime, timedelta
from models import User, Message, UserTheme, Subscription, MessageContext
from typing import Optional, Tuple
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

def save_message(user_id: int, content: str, is_from_user: bool, theme: str = None, sentiment_score: float = None) -> Message:
    print(f"[Database] Attempting to save message for user {user_id}")
    with get_db_session() as db:
        try:
            message = Message(
                user_id=user_id,
                content=content,
                is_from_user=is_from_user,
                theme=theme,
                sentiment_score=sentiment_score
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

def verify_user_deletion(db, user_id: int) -> Tuple[bool, str]:
    """Verify that all user data has been properly deleted."""
    try:
        remaining_user = db.query(User).filter(User.id == user_id).first()
        remaining_messages = db.query(Message).filter(Message.user_id == user_id).count()
        remaining_themes = db.query(UserTheme).filter(UserTheme.user_id == user_id).count()
        remaining_subscriptions = db.query(Subscription).filter(Subscription.user_id == user_id).count()

        if any([remaining_user, remaining_messages, remaining_themes, remaining_subscriptions]):
            error_msg = "Deletion verification failed. Remaining data: "
            if remaining_user:
                error_msg += "User record exists; "
            if remaining_messages:
                error_msg += f"{remaining_messages} messages; "
            if remaining_themes:
                error_msg += f"{remaining_themes} themes; "
            if remaining_subscriptions:
                error_msg += f"{remaining_subscriptions} subscriptions; "
            return False, error_msg.strip("; ")
        
        return True, "All user data successfully deleted and verified"
    except Exception as e:
        return False, f"Error during deletion verification: {str(e)}"

def delete_user_data(user_id: int, db) -> Tuple[bool, str]:
    """Delete all data associated with a user with detailed verification."""
    print(f"[Database] Starting data deletion for user ID: {user_id}")
    
    try:
        # Verify user exists before deletion
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False, f"User with ID {user_id} not found"

        # Get counts before deletion for verification
        initial_messages = db.query(Message).filter(Message.user_id == user_id).count()
        initial_themes = db.query(UserTheme).filter(UserTheme.user_id == user_id).count()
        initial_subscriptions = db.query(Subscription).filter(Subscription.user_id == user_id).count()
        
        print(f"[Database] Found data to delete: {initial_messages} messages, {initial_themes} themes, {initial_subscriptions} subscriptions")

        # Delete message contexts first (due to foreign key relationships)
        message_ids = db.query(Message.id).filter(Message.user_id == user_id).all()
        if message_ids:
            message_id_list = [m.id for m in message_ids]
            deleted_contexts = db.query(MessageContext).filter(
                MessageContext.message_id.in_(message_id_list)
            ).delete(synchronize_session=False)
            print(f"[Database] Deleted {deleted_contexts} message contexts")
        
        # Delete messages
        deleted_messages = db.query(Message).filter(Message.user_id == user_id).delete()
        print(f"[Database] Deleted {deleted_messages} messages")
        
        # Delete subscription records
        deleted_subscriptions = db.query(Subscription).filter(
            Subscription.user_id == user_id
        ).delete()
        print(f"[Database] Deleted {deleted_subscriptions} subscription records")
        
        # Delete user themes
        deleted_themes = db.query(UserTheme).filter(
            UserTheme.user_id == user_id
        ).delete()
        print(f"[Database] Deleted {deleted_themes} user themes")
        
        # Finally delete the user
        deleted_user = db.query(User).filter(User.id == user_id).delete()
        print(f"[Database] Deleted user record: {deleted_user}")
        
        # Verify deletion
        is_verified, verification_message = verify_user_deletion(db, user_id)
        if not is_verified:
            db.rollback()
            return False, f"Deletion failed: {verification_message}"
        
        # If everything is successful, return True
        print("[Database] Successfully deleted and verified all user data")
        return True, "All user data successfully deleted and verified"
        
    except Exception as e:
        error_message = f"Error deleting user data: {str(e)}"
        print(f"[Database] {error_message}")
        raise Exception(error_message)



def get_message_context(user_id: int, limit: int = 5, context_window: int = 24) -> list[Message]:
    """Get recent message context for a user within the specified time window."""
    with get_db_session() as db:
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=context_window)
            return db.query(Message).filter(
                Message.user_id == user_id,
                Message.timestamp >= cutoff_time
            ).order_by(Message.timestamp.desc()).limit(limit).all()
        except Exception as e:
            print(f"[Database] Error retrieving message context: {str(e)}")
            return []

def save_message_context(message_id: int, context_data: dict, expiry_hours: int = 24) -> bool:
    """Save context information for a message."""
    with get_db_session() as db:
        try:
            expires_at = datetime.utcnow() + timedelta(hours=expiry_hours)
            contexts = [
                MessageContext(
                    message_id=message_id,
                    context_key=key,
                    context_value=str(value),
                    relevance_score=1.0,
                    expires_at=expires_at
                )
                for key, value in context_data.items()
            ]
            db.add_all(contexts)
            db.commit()
            return True
        except Exception as e:
            print(f"[Database] Error saving message context: {str(e)}")
            db.rollback()
            return False

def clean_expired_context():
    """Remove expired context entries."""
    with get_db_session() as db:
        try:
            db.query(MessageContext).filter(
                MessageContext.expires_at < datetime.utcnow()
            ).delete()
            db.commit()
            return True
        except Exception as e:
            print(f"[Database] Error cleaning expired context: {str(e)}")
            db.rollback()
            return False
