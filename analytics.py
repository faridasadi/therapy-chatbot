from datetime import datetime, timedelta
from sqlalchemy import func
from db import get_db_session
from models import User, Message, UserTheme, Subscription

def get_user_growth_data():
    """Get user registration data over time."""
    db = get_db_session()
    try:
        users = db.query(
            func.date_trunc('day', User.joined_at).label('date'),
            func.count(User.id).label('count')
        ).group_by(func.date_trunc('day', User.joined_at))\
         .order_by('date').all()
        
        return {
            'dates': [u.date.strftime('%Y-%m-%d') for u in users],
            'counts': [u.count for u in users]
        }
    finally:
        db.close()

def get_message_activity_data():
    """Get message activity data."""
    db = get_db_session()
    try:
        messages = db.query(
            func.date_trunc('day', Message.timestamp).label('date'),
            func.count(Message.id).label('count')
        ).group_by(func.date_trunc('day', Message.timestamp))\
         .order_by('date').all()
        
        return {
            'dates': [m.date.strftime('%Y-%m-%d') for m in messages],
            'counts': [m.count for m in messages]
        }
    finally:
        db.close()

def get_subscription_metrics():
    """Get subscription-related metrics."""
    db = get_db_session()
    try:
        total_users = db.query(func.count(User.id)).scalar()
        subscribed_users = db.query(func.count(User.id))\
            .filter(User.is_subscribed == True).scalar()
        total_revenue = db.query(func.sum(Subscription.amount))\
            .filter(Subscription.status == 'active').scalar() or 0
        
        return {
            'total_users': total_users,
            'subscribed_users': subscribed_users,
            'subscription_rate': round((subscribed_users / total_users * 100) if total_users > 0 else 0, 2),
            'total_revenue': round(total_revenue, 2)
        }
    finally:
        db.close()

def get_theme_distribution():
    """Get distribution of conversation themes."""
    db = get_db_session()
    try:
        themes = db.query(
            UserTheme.theme,
            func.count(UserTheme.id).label('count')
        ).group_by(UserTheme.theme)\
         .order_by(func.count(UserTheme.id).desc())\
         .limit(10).all()
        
        return {
            'themes': [t.theme for t in themes],
            'counts': [t.count for t in themes]
        }
    finally:
        db.close()

def get_sentiment_over_time():
    """Get average sentiment scores over time."""
    db = get_db_session()
    try:
        sentiments = db.query(
            func.date_trunc('day', Message.timestamp).label('date'),
            func.avg(Message.sentiment_score).label('average_sentiment')
        ).filter(Message.sentiment_score.isnot(None))\
         .group_by(func.date_trunc('day', Message.timestamp))\
         .order_by('date').all()
        
        return {
            'dates': [s.date.strftime('%Y-%m-%d') for s in sentiments],
            'scores': [float(s.average_sentiment) for s in sentiments]
        }
    finally:
        db.close()
