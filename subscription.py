from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app import get_db_session
from models import User, Subscription
from config import (
    SUBSCRIPTION_PRICE,
    SUBSCRIPTION_DESCRIPTION,
    PAYMENT_CURRENCY,
    TELEGRAM_PAYMENT_PROVIDER_TOKEN
)
from telegram import LabeledPrice

def generate_payment_invoice(user_id: int) -> dict:
    """Generate payment invoice data for Telegram Payments."""
    try:
        return {
            'title': 'Therapyyy Monthly Subscription',
            'description': SUBSCRIPTION_DESCRIPTION,
            'payload': f'sub_{user_id}_{datetime.utcnow().timestamp()}',
            'provider_token': TELEGRAM_PAYMENT_PROVIDER_TOKEN,
            'currency': PAYMENT_CURRENCY,
            'prices': [LabeledPrice(label='Monthly Subscription', amount=int(SUBSCRIPTION_PRICE * 100))]
        }
    except Exception as e:
        print(f"Error generating payment invoice: {e}")
        return None

def create_subscription(user_id: int, payment_id: str) -> bool:
    db = get_db_session()
    try:
        user = db.query(User).get(user_id)
        if not user:
            return False
            
        subscription = Subscription(
            user_id=user_id,
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=30),
            payment_id=payment_id,
            amount=SUBSCRIPTION_PRICE,
            status='active'
        )
        
        user.is_subscribed = True
        user.subscription_end = subscription.end_date
        
        db.add(subscription)
        db.commit()
        return True
        
    except Exception:
        db.rollback()
        return False
    finally:
        db.close()

def cancel_subscription(user_id: int) -> bool:
    db = get_db_session()
    try:
        user = db.query(User).get(user_id)
        if not user:
            return False
            
        subscription = db.query(Subscription).filter_by(
            user_id=user_id,
            status='active'
        ).first()
        
        if subscription:
            subscription.status = 'cancelled'
            user.is_subscribed = False
            user.subscription_end = datetime.utcnow()
            db.commit()
            
        return True
        
    except Exception:
        db.rollback()
        return False
    finally:
        db.close()


def check_subscription_status(user_id: int) -> bool:
    """Check if user has an active subscription."""
    db = get_db_session()
    try:
        user = db.query(User).get(user_id)
        if not user:
            return False
        return user.is_subscribed and user.subscription_end > datetime.utcnow()
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
        if user.messages_count >= 20 or user.weekly_messages_count >= 20:
            return False, 0

        # Increment message counts
        user.messages_count += 1
        user.weekly_messages_count += 1
        db.commit()

        remaining = min(20 - user.messages_count, 20 - user.weekly_messages_count)
        return True, remaining

    except Exception:
        db.rollback()
        return False, 0
    finally:
        db.close()

def save_message(user_id: int, content: str, is_from_user: bool) -> bool:
    """Save a message to the database."""
    db = get_db_session()
    try:
        message = Message(
            user_id=user_id,
            content=content,
            is_from_user=is_from_user
        )
        db.add(message)
        db.commit()
        return True
    except Exception:
        db.rollback()
        return False
    finally:
        db.close()