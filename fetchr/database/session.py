from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from fetchr.database.models import Base

# Default to a local SQLite database in the user's home directory or project directory
DB_PATH = Path("fetchr.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL, 
    connect_args={"check_same_thread": False}, # Needed for SQLite with multithreading
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)

# Scoped session for thread safety if needed
db_session = scoped_session(SessionLocal)

def init_db():
    """Create tables if they don't exist"""
    Base.metadata.create_all(bind=engine)

def get_db():
    """Dependency for getting a DB session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
