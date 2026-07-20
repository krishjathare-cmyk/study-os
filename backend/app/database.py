import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from app.storage import BACKEND_DIR, DATA_DIR

load_dotenv(dotenv_path=BACKEND_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./study_assistant.db")
is_sqlite = DATABASE_URL.startswith("sqlite")

# Resolve relative SQLite files from APP_DATA_DIR, not the current shell
# directory. Setting APP_DATA_DIR to a mounted volume therefore persists the
# database without requiring a separate DATABASE_URL override.
if DATABASE_URL.startswith("sqlite:///./"):
    relative_path = DATABASE_URL[len("sqlite:///./"):]
    database_path = (DATA_DIR / Path(relative_path)).resolve()
    DATABASE_URL = f"sqlite:///{database_path.as_posix()}"

connect_args = {}
if is_sqlite:
    connect_args = {
        "check_same_thread": False,
        "timeout": 60,
    }

engine = create_engine(DATABASE_URL, connect_args=connect_args)


if is_sqlite:
    @event.listens_for(engine, "connect")
    def configure_sqlite(connection, _):
        cursor = connection.cursor()
        try:
            cursor.execute("PRAGMA busy_timeout=60000")
            cursor.execute("PRAGMA foreign_keys=ON")

            try:
                cursor.execute("PRAGMA journal_mode=WAL")
            except sqlite3.OperationalError as exc:
                if "database is locked" not in str(exc).lower():
                    raise
        finally:
            cursor.close()

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
