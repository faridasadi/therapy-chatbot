from datetime import datetime, timedelta
from app import db
from models import User, Message, Subscription
from config import FREE_MESSAGE_LIMIT, WEEKLY_FREE_MESSAGES

def get_or_create_user(telegram_id: int, username: str = None, first_name: str = None) -> User:
    user = User.query.get(telegram_id)
    if not user:
        user = User(
            id=telegram_id,
            username=username,
            first_name=first_name,
            messages_count=0
        )
        db.session.add(user)
        db.session.commit()
    return user

def save_message(user_id: int, content: str, is_from_user: bool) -> Message:
    print(f"[Database] Attempting to save message for user {user_id}")
    try:
        message = Message(
            user_id=user_id,
            content=content,
            is_from_user=is_from_user
        )
        print(f"[Database] Message object created, length: {len(content)} chars")
        
        db.session.add(message)
        print(f"[Database] Message added to session")
        
        db.session.commit()
        print(f"[Database] Message successfully saved with ID: {message.id}")
        return message
    except Exception as e:
        print(f"[Database] Error saving message: {str(e)}")
        db.session.rollback()
        raise

def increment_message_count(user_id: int) -> tuple[bool, int]:
    print(f"[Database] Checking message count for user {user_id}")
    user = User.query.get(user_id)
    if not user:
        print(f"[Database] User {user_id} not found")
        return False, 0
        
    # Reset weekly messages if needed
    if datetime.utcnow() - user.last_message_reset > timedelta(days=7):
        user.weekly_messages_count = 0
        user.last_message_reset = datetime.utcnow()
    
    user.messages_count += 1
    user.weekly_messages_count += 1
    db.session.commit()
    
    if user.is_subscribed:
        return True, -1
    
    remaining = FREE_MESSAGE_LIMIT - user.messages_count
    if remaining < 0 and user.weekly_messages_count > WEEKLY_FREE_MESSAGES:
        return False, 0
        
    return True, remaining

def check_subscription_status(user_id: int) -> bool:
    user = User.query.get(user_id)
    if not user:
        return False
        
    if not user.is_subscribed:
        return False
        
    if user.subscription_end and user.subscription_end < datetime.utcnow():
        user.is_subscribed = False
        db.session.commit()
        return False
        
    return True
