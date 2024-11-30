from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, BigInteger, Text, Float, ForeignKey
from sqlalchemy.orm import relationship
from app import Base

class User(Base):
    __tablename__ = 'user'
    
    id = Column(BigInteger, primary_key=True)  # Telegram user ID
    username = Column(String(64))
    first_name = Column(String(64))
    joined_at = Column(DateTime, default=datetime.utcnow)
    is_subscribed = Column(Boolean, default=False)
    subscription_end = Column(DateTime, nullable=True)
    messages_count = Column(Integer, default=0)
    weekly_messages_count = Column(Integer, default=0)
    last_message_reset = Column(DateTime, default=datetime.utcnow)
    subscription_prompt_views = Column(Integer, default=0)
    
    messages = relationship("Message", back_populates="user")
    subscriptions = relationship("Subscription", back_populates="user")

class Message(Base):
    __tablename__ = 'message'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('user.id'))
    content = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)
    is_from_user = Column(Boolean)
    
    user = relationship("User", back_populates="messages")

class Subscription(Base):
    __tablename__ = 'subscription'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('user.id'))
    start_date = Column(DateTime, default=datetime.utcnow)
    end_date = Column(DateTime)
    payment_id = Column(String(128))
    amount = Column(Float)
    status = Column(String(32))
    
    user = relationship("User", back_populates="subscriptions")
