from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app import get_db_session
from models import User, Message, Subscription
from config import FREE_MESSAGE_LIMIT, WEEKLY_FREE_MESSAGES

def get_or_create_user(telegram_id: int, username: str = None, first_name: str = None) -> User:
    db = get_db_session()
    try:
        user = db.query(User).get(telegram_id)
        if not user:
            user = User(
                id=telegram_id,
                username=username,
                first_name=first_name,
                messages_count=0
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        return user
    finally:
        db.close()

def save_message(user_id: int, content: str, is_from_user: bool) -> Message:
    print(f"[Database] Attempting to save message for user {user_id}")
    db = get_db_session()
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
    finally:
        db.close()

def increment_message_count(user_id: int) -> tuple[bool, int]:
    print(f"[Database] Checking message count for user {user_id}")
    db = get_db_session()
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
    finally:
        db.close()

def check_subscription_status(user_id: int) -> bool:
    db = get_db_session()
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
    finally:
        db.close()


def clean_user_data(user_id: int) -> bool:
    """Clean up all user data and reset background information.
    
    Args:
        user_id: The Telegram user ID to clean up
        
    Returns:
        bool: True if cleanup was successful, False otherwise
    """
    print(f"[Database] Starting data cleanup for user {user_id}")
    db = get_db_session()
    
    try:
        with db.begin():
            # Get the user
            user = db.query(User).get(user_id)
            if not user:
                print(f"[Database] User {user_id} not found")
                return False
                
            # Delete all messages
            db.query(Message).filter(Message.user_id == user_id).delete()
            
            # Delete all themes
            db.query(UserTheme).filter(UserTheme.user_id == user_id).delete()
            
            # Delete all subscriptions
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
    finally:
        db.close()
