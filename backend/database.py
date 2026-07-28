"""SQLAlchemy engine, session, and declarative base for LeadFlow AI."""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./leadflow.db")

# check_same_thread=False is required because FastAPI can access the
# connection from different threads under SQLite.
engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a DB session and closes it after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables. Safe to call multiple times."""
    from backend import models  # noqa: F401  (ensures models are registered)

    Base.metadata.create_all(bind=engine)
