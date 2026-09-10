"""SQLAlchemy engine/session setup. Works against PostgreSQL (runtime) or
SQLite (tests) since the models avoid dialect-specific types."""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings

_engine_kwargs = {"future": True}
if settings.DATABASE_URL.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
    if ":memory:" in settings.DATABASE_URL:
        _engine_kwargs["poolclass"] = StaticPool

engine = create_engine(settings.DATABASE_URL, **_engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from app import models  # noqa: F401  (ensure models are registered)

    Base.metadata.create_all(bind=engine)
