from sqlalchemy import create_engine
from sqlalchemy import event, select, exc
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import QueuePool
from contextlib import contextmanager
import os
from datetime import datetime, timedelta
from typing import Optional, Tuple, List, Dict
from config import FREE_MESSAGE_LIMIT, WEEKLY_FREE_MESSAGES
import logging
from functools import lru_cache
from models import User, Message, UserTheme, Subscription, MessageContext
from base import Base

# Configure logging
logger = logging.getLogger(__name__)

# Telegram-only optimized engine configuration
engine = create_engine(
    os.getenv('DATABASE_URL'),
    poolclass=QueuePool,
    pool_size=2,  # Reduced pool size for Telegram-only
    max_overflow=2,  # Minimal overflow for Telegram traffic
    pool_timeout=5,  # Faster timeout for better error detection
    pool_recycle=600,  # Recycle connections every 10 minutes
    pool_pre_ping=True,  # Connection verification
    echo_pool=False,  # Production logging
    connect_args={
        'connect_timeout': 5,  # Reduced connection timeout
        'application_name': 'telegram_therapy_bot',
        'options': '-c statement_timeout=5000'  # 5 second query timeout
    }
)

# Enhanced error handling for connection pool
from sqlalchemy import event
@event.listens_for(engine, 'engine_connect')
def ping_connection(connection, branch):
    if branch:
        return

    try:
        connection.scalar(select(1))
    except exc.DBAPIError as err:
        if err.connection_invalidated:
            connection.scalar(select(1))
        else:
            raise

# LRU Cache for frequently accessed users
@lru_cache(maxsize=100)
def get_cached_user(user_id: int) -> Optional[User]:
    """Get user from cache or database with 5-minute TTL."""
    with get_db_session() as db:
        return db.query(User).get(user_id)

# Create session factory
SessionFactory = sessionmaker(bind=engine)
ScopedSession = scoped_session(SessionFactory)

@contextmanager
def get_db_session():
    """Enhanced context manager for database sessions with proper cleanup"""
    session = ScopedSession()
    try:
        yield session
    except Exception as e:
        logger.error(f"Database session error: {str(e)}")
        session.rollback()
        raise
    finally:
        try:
            session.close()
        except Exception as e:
            logger.error(f"Error closing session: {str(e)}")
        finally:
            ScopedSession.remove()

def init_database():
    """Initialize database tables"""
    Base.metadata.create_all(bind=engine)

# Rest of the existing database.py content...
from models import User, Message, UserTheme, Subscription, MessageContext

def get_or_create_user(user_id: int, username: Optional[str] = None, first_name: Optional[str] = None) -> User:
    """Get or create a user with caching"""
    # Try to get user from cache first
    cached_user = get_cached_user(user_id)
    if cached_user:
        return cached_user

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
            db.refresh(user)
            
            # Invalidate cache for this user_id
            get_cached_user.cache_clear()
            
        return user

from typing import List, Optional
from sqlalchemy.orm import Session
from collections import defaultdict
import threading
from queue import Queue
import time

# Message batch processing
_message_queue: Queue = Queue()
_batch_size = 50
_batch_timeout = 5  # seconds
_last_batch_time = time.time()
_batch_lock = threading.Lock()

def _process_message_batch():
    """Process queued messages in batches."""
    messages_to_process = []
    try:
        while len(messages_to_process) < _batch_size:
            try:
                msg_data = _message_queue.get_nowait()
                messages_to_process.append(msg_data)
            except Queue.Empty:
                break

        if messages_to_process:
            with get_db_session() as db:
                messages = [
                    Message(
                        user_id=msg['user_id'],
                        content=msg['content'],
                        is_from_user=msg['is_from_user'],
                        theme=msg['theme'],
                        sentiment_score=msg['sentiment_score']
                    )
                    for msg in messages_to_process
                ]
                db.add_all(messages)
                db.commit()
                
                # Refresh all messages to get their IDs
                for msg in messages:
                    db.refresh(msg)
                
                logger.info(f"Batch saved {len(messages)} messages successfully")
                return messages
    except Exception as e:
        logger.error(f"Error in batch message processing: {str(e)}")
        if 'db' in locals():
            db.rollback()
        raise
    return []

def save_message(user_id: int, content: str, is_from_user: bool, theme: str = None, sentiment_score: float = None) -> Message:
    """Queue message for batch processing."""
    logger.info(f"Queueing message for user {user_id}")
    message_data = {
        'user_id': user_id,
        'content': content,
        'is_from_user': is_from_user,
        'theme': theme,
        'sentiment_score': sentiment_score
    }
    
    _message_queue.put(message_data)
    
    # Process batch if size threshold reached or timeout elapsed
    with _batch_lock:
        global _last_batch_time
        current_time = time.time()
        
        if _message_queue.qsize() >= _batch_size or (current_time - _last_batch_time) >= _batch_timeout:
            messages = _process_message_batch()
            _last_batch_time = current_time
            
            # Return the specific message for this request
            if messages:
                return next(
                    (msg for msg in messages 
                     if msg.user_id == user_id and msg.content == content),
                    messages[-1]  # Fallback to last message if specific one not found
                )
    
    # If we didn't process a batch, create a single message
    with get_db_session() as db:
        message = Message(**message_data)
        db.add(message)
        db.commit()
        db.refresh(message)
        return message

def increment_message_count(user_id: int) -> tuple[bool, int]:
    logger.info(f"Checking message count for user {user_id}")
    with get_db_session() as db:
        try:
            user = db.query(User).get(user_id)
            if not user:
                logger.warning(f"User {user_id} not found")
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
            logger.error(f"Error incrementing message count: {str(e)}")
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
            logger.error(f"Error checking subscription status: {str(e)}")
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

def clean_user_data(user_id: int) -> bool:
    """Clean up all user data and reset background information."""
    print(f"[Database] Starting data cleanup for user {user_id}")

    with get_db_session() as db:
        try:
            with db.begin():
                user = db.query(User).get(user_id)
                if not user:
                    logger.warning(f"User {user_id} not found")
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