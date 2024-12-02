from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# Create engine with optimized connection pooling and query timeout
engine = create_engine(
    os.getenv('DATABASE_URL'),
    pool_size=10,  # Reduced pool size for better resource management
    max_overflow=20,  # Balanced overflow connections
    pool_timeout=30,  # Reduced timeout to fail fast
    pool_recycle=300,  # More frequent connection recycling
    pool_pre_ping=True,  # Enable connection health checks
    echo_pool=True,  # Log pool events for monitoring
    connect_args={
        'connect_timeout': 5,  # Reduced connection timeout
        'statement_timeout': 15000,  # Reduced statement timeout (15 seconds)
        'lock_timeout': 5000,  # Reduced lock timeout (5 seconds)
        'options': '-c synchronous_commit=off -c work_mem=64MB -c maintenance_work_mem=128MB'  # Performance optimizations
    }
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create declarative base
Base = declarative_base()
