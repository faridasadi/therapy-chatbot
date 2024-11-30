from datetime import datetime, timedelta
from app import db
from models import User, Subscription
from config import SUBSCRIPTION_PRICE

def create_subscription(user_id: int, payment_id: str) -> bool:
    try:
        user = User.query.get(user_id)
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
        
        db.session.add(subscription)
        db.session.commit()
        return True
        
    except Exception:
        db.session.rollback()
        return False

def cancel_subscription(user_id: int) -> bool:
    try:
        user = User.query.get(user_id)
        if not user:
            return False
            
        subscription = Subscription.query.filter_by(
            user_id=user_id,
            status='active'
        ).first()
        
        if subscription:
            subscription.status = 'cancelled'
            user.is_subscribed = False
            user.subscription_end = datetime.utcnow()
            db.session.commit()
            
        return True
        
    except Exception:
        db.session.rollback()
        return False
