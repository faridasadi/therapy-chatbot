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
