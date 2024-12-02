from datetime import datetime, timedelta
from sqlalchemy import func, and_, text
from db import get_db_session
from models import User, Message, UserTheme, Subscription
from functools import lru_cache, wraps
from typing import Dict, List, Any
import time

def timed_lru_cache(seconds: int, maxsize: int = 128):
    def wrapper_decorator(func):
        func = lru_cache(maxsize=maxsize)(func)
        func.lifetime = seconds
        func.expiration = time.time() + seconds

        @wraps(func)
        def wrapped_func(*args, **kwargs):
            if time.time() > func.expiration:
                func.cache_clear()
                func.expiration = time.time() + func.lifetime
            return func(*args, **kwargs)

        return wrapped_func
    return wrapper_decorator

@timed_lru_cache(seconds=300, maxsize=100)  # Cache results for 5 minutes
def get_user_growth_data():
    """Get user registration data over time."""
    db = get_db_session()
    try:
        # Use a materialized CTE for better performance
        users = db.query(
            func.date_trunc('day', User.joined_at).label('date'),
            func.count(User.id).label('count')
        ).group_by(func.date_trunc('day', User.joined_at))\
         .order_by('date')\
         .all()
        
        return {
            'dates': [u.date.strftime('%Y-%m-%d') for u in users],
            'counts': [u.count for u in users]
        }
    finally:
        db.close()

@timed_lru_cache(seconds=300, maxsize=100)
def get_message_activity_data():
    """Get message activity data with efficient querying and caching."""
    db = get_db_session()
    try:
        # Use window function for better performance
        query = text("""
            WITH daily_messages AS (
                SELECT date_trunc('day', timestamp) as date,
                       count(*) as count
                FROM message
                WHERE timestamp >= current_date - interval '30 days'
                GROUP BY date_trunc('day', timestamp)
            )
            SELECT date, count
            FROM daily_messages
            ORDER BY date
        """)
        
        result = db.execute(query).fetchall()
        
        return {
            'dates': [row.date.strftime('%Y-%m-%d') for row in result],
            'counts': [row.count for row in result]
        }
    finally:
        db.close()

@timed_lru_cache(seconds=60, maxsize=1)  # Cache for 1 minute
def get_subscription_metrics():
    """Get subscription-related metrics."""
    db = get_db_session()
    try:
        # Use a single query with multiple aggregations
        metrics = db.query(
            func.count(User.id).label('total_users'),
            func.sum(case((User.is_subscribed == True, 1), else_=0)).label('subscribed_users'),
            func.coalesce(
                func.sum(case((Subscription.status == 'active', Subscription.amount), else_=0)),
                0
            ).label('total_revenue')
        ).outerjoin(Subscription).first()
        
        return {
            'total_users': metrics.total_users,
            'subscribed_users': metrics.subscribed_users,
            'subscription_rate': round((metrics.subscribed_users / metrics.total_users * 100) 
                                    if metrics.total_users > 0 else 0, 2),
            'total_revenue': round(float(metrics.total_revenue), 2)
        }
    finally:
        db.close()

@timed_lru_cache(seconds=300, maxsize=1)
def get_theme_distribution():
    """Get distribution of conversation themes."""
    db = get_db_session()
    try:
        # Use materialized query for theme distribution
        query = text("""
            WITH theme_counts AS (
                SELECT theme,
                       count(*) as theme_count,
                       row_number() OVER (ORDER BY count(*) DESC) as rn
                FROM user_theme
                GROUP BY theme
            )
            SELECT theme, theme_count
            FROM theme_counts
            WHERE rn <= 10
            ORDER BY theme_count DESC
        """)
        
        themes = db.execute(query).fetchall()
        
        return {
            'themes': [t.theme for t in themes],
            'counts': [t.theme_count for t in themes]
        }
    finally:
        db.close()

@timed_lru_cache(seconds=300, maxsize=1)
def get_sentiment_over_time():
    """Get average sentiment scores over time."""
    db = get_db_session()
    try:
        # Use window function for efficient sentiment calculation
        query = text("""
            WITH daily_sentiment AS (
                SELECT date_trunc('day', timestamp) as date,
                       avg(sentiment_score) as average_sentiment
                FROM message
                WHERE sentiment_score IS NOT NULL
                GROUP BY date_trunc('day', timestamp)
            )
            SELECT date, average_sentiment
            FROM daily_sentiment
            ORDER BY date
        """)
        
        sentiments = db.execute(query).fetchall()
        
        return {
            'dates': [s.date.strftime('%Y-%m-%d') for s in sentiments],
            'scores': [float(s.average_sentiment) for s in sentiments]
        }
    finally:
        db.close()
