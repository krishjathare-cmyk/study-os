import os
import sqlite3
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./study_assistant.db")
is_sqlite = DATABASE_URL.startswith("sqlite")

# Resolve the default SQLite file from the backend directory, not the shell's
# current directory. This keeps Uvicorn launches from different folders on the
# same database.
if DATABASE_URL.startswith("sqlite:///./"):
    relative_path = DATABASE_URL[len("sqlite:///./"):]
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    database_path = os.path.abspath(os.path.join(backend_dir, relative_path))
    DATABASE_URL = f"sqlite:///{database_path.replace(os.sep, '/') }"

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
