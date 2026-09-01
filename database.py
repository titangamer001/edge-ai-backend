import os
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
import datetime
from dotenv import load_dotenv

load_dotenv() # Load variables from .env file if it exists

# Default to SQLite locally, but use PostgreSQL if provided in cloud
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./edge_data.db")

# SQLAlchemy 1.4+ requires "postgresql://" instead of "postgres://"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Only SQLite needs check_same_thread
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    print(f"DEBUG URL: {DATABASE_URL}")
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Device(Base):
    __tablename__ = "devices"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(255), unique=True, index=True)
    name = Column(String(255))
    location = Column(String(255))
    device_type = Column(String(255))
    status = Column(String(255), default="online")
    last_seen = Column(DateTime, default=datetime.datetime.utcnow)
    health_score = Column(Float, default=100.0)

class Telemetry(Base):
    __tablename__ = "telemetry"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    device_id = Column(String(255), index=True)
    latency = Column(Float)
    packet_loss = Column(Float)
    bandwidth = Column(Float)
    
class Alert(Base):
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    device_id = Column(String(255), index=True)
    alert_type = Column(String(255))
    severity = Column(String(255)) # critical, high, medium, low
    message = Column(String(1024))
    current_value = Column(Float)
    threshold = Column(Float)
    status = Column(String(255), default="active") # active, resolved, acknowledged

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    discord_id = Column(String(255), unique=True, index=True)
    username = Column(String(255))
    avatar_url = Column(String(255))
    last_login = Column(DateTime, default=datetime.datetime.utcnow)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
