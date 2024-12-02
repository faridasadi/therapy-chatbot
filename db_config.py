from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# Create engine with optimized connection pooling and query timeout
engine = create_engine(
    os.getenv('DATABASE_URL'),
    pool_size=20,  # Optimized for concurrent handling
    max_overflow=30,  # Allow more overflow connections
    pool_timeout=60,  # Increased timeout for busy periods
    pool_recycle=1200,  # Reduced recycle time to prevent stale connections
    pool_pre_ping=True,  # Enable connection health checks
    echo_pool=True,  # Log pool events for monitoring
    connect_args={
        'connect_timeout': 10,  # Connection timeout in seconds
        'statement_timeout': 30000,  # Statement timeout in milliseconds (30 seconds)
        'lock_timeout': 10000,  # Lock timeout in milliseconds (10 seconds)
        'options': '-c synchronous_commit=off'  # Improve write performance
    }
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create declarative base
Base = declarative_base()
