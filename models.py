from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, BigInteger, Text, Float, ForeignKey, Index
from sqlalchemy.orm import relationship, backref
from base import Base

class User(Base):
    __tablename__ = 'user'
    
    __table_args__ = (
        Index('idx_user_subscription', 'is_subscribed'),
        Index('idx_user_message_counts', 'messages_count', 'weekly_messages_count'),
        Index('idx_user_last_reset', 'last_message_reset'),
        Index('idx_user_interaction', 'interaction_style'),
    )
    
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
    interaction_style = Column(String(50), default='balanced')  # Store user's preferred interaction style
    # Background information fields
    age = Column(Integer, nullable=True)
    gender = Column(String(32), nullable=True)
    therapy_experience = Column(String(255), nullable=True)
    primary_concerns = Column(String(500), nullable=True)
    background_completed = Column(Boolean, default=False)
    
    messages = relationship("Message", back_populates="user")
    subscriptions = relationship("Subscription", back_populates="user")
    themes = relationship("UserTheme", back_populates="user")

class UserTheme(Base):
    __tablename__ = 'user_theme'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('user.id'))
    theme = Column(String(100))
    sentiment = Column(Float)  # Store sentiment score for the theme
    frequency = Column(Integer, default=1)
    last_mentioned = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="themes")

class Message(Base):
    __tablename__ = 'message'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('user.id'))
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_from_user = Column(Boolean)
    role = Column(String(50), nullable=True)  # System, user, or assistant
    theme = Column(String(100), nullable=True)  # Store identified theme
    sentiment_score = Column(Float, nullable=True)  # Store message sentiment
    
    __table_args__ = (
        Index('idx_message_user_time', user_id, created_at),
        Index('idx_message_theme', theme),
    )
    
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


class MessageContext(Base):
    __tablename__ = 'message_context'
    
    id = Column(Integer, primary_key=True)
    message_id = Column(Integer, ForeignKey('message.id', ondelete='CASCADE'))
    context_key = Column(String(100))  # Type of context (e.g., 'emotion', 'topic', 'intent')
    context_value = Column(Text)
    relevance_score = Column(Float)  # How relevant this context is (0-1)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)  # When this context should expire
    
    message = relationship("Message", backref=backref("contexts", cascade="all, delete-orphan"))

    __table_args__ = (
        Index('idx_message_context_expires', expires_at),  # Index for context cleanup
        Index('idx_message_context_message_key', message_id, context_key),  # Composite index for faster lookups
        Index('idx_message_context_active', expires_at, relevance_score,  # Partial index for active contexts
              postgresql_where=expires_at > datetime.utcnow())
    )