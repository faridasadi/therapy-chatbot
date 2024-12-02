from datetime import datetime, timedelta
from sqlalchemy import func, and_, text, case
from db import get_db_session
from models import User, Message, UserTheme, Subscription
from typing import Dict, Any
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
    """Get message activity data using materialized view for better performance."""
    db = get_db_session()
    try:
        query = text("""
            SELECT date, message_count as count
            FROM mv_daily_message_stats
            WHERE date >= current_date - interval '30 days'
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
def get_subscription_metrics() -> Dict[str, Any]:
    """Get subscription-related metrics with optimized querying."""
    db = get_db_session()
    try:
        # Use materialized query with proper indexing
        metrics_query = text("""
            WITH user_metrics AS (
                SELECT 
                    COUNT(*) as total_users,
                    SUM(CASE WHEN is_subscribed THEN 1 ELSE 0 END) as subscribed_users
                FROM "user"
            ),
            revenue_metrics AS (
                SELECT COALESCE(SUM(amount), 0) as total_revenue
                FROM subscription
                WHERE status = 'active'
            )
            SELECT 
                um.total_users,
                um.subscribed_users,
                rm.total_revenue
            FROM user_metrics um
            CROSS JOIN revenue_metrics rm
        """)
        
        result = db.execute(metrics_query).first()
        
        if not result:
            return {
                'total_users': 0,
                'subscribed_users': 0,
                'subscription_rate': 0,
                'total_revenue': 0.0
            }
        
        total_users = result.total_users or 0
        subscribed_users = result.subscribed_users or 0
        
        return {
            'total_users': total_users,
            'subscribed_users': subscribed_users,
            'subscription_rate': round((subscribed_users / total_users * 100) 
                                    if total_users > 0 else 0, 2),
            'total_revenue': round(float(result.total_revenue), 2)
        }
    except Exception as e:
        print(f"Error fetching subscription metrics: {e}")
        return {
            'total_users': 0,
            'subscribed_users': 0,
            'subscription_rate': 0,
            'total_revenue': 0.0
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
    """Get average sentiment scores over time using materialized view."""
    db = get_db_session()
    try:
        query = text("""
            SELECT date, avg_sentiment as average_sentiment
            FROM mv_daily_message_stats
            WHERE date >= current_date - interval '30 days'
                AND avg_sentiment IS NOT NULL
            ORDER BY date
        """)
        
        sentiments = db.execute(query).fetchall()
        
        return {
            'dates': [s.date.strftime('%Y-%m-%d') for s in sentiments],
            'scores': [float(s.average_sentiment) for s in sentiments]
        }
    finally:
        db.close()
