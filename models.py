from datetime import datetime
from app import db

class User(db.Model):
    id = db.Column(db.BigInteger, primary_key=True)  # Telegram user ID
    username = db.Column(db.String(64))
    first_name = db.Column(db.String(64))
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_subscribed = db.Column(db.Boolean, default=False)
    subscription_end = db.Column(db.DateTime, nullable=True)
    messages_count = db.Column(db.Integer, default=0)
    weekly_messages_count = db.Column(db.Integer, default=0)
    last_message_reset = db.Column(db.DateTime, default=datetime.utcnow)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey('user.id'))
    content = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_from_user = db.Column(db.Boolean)

class Subscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey('user.id'))
    start_date = db.Column(db.DateTime, default=datetime.utcnow)
    end_date = db.Column(db.DateTime)
    payment_id = db.Column(db.String(128))
    amount = db.Column(db.Float)
    status = db.Column(db.String(32))
