"""Engine and session factory for the metadata database."""

from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from ichnos.settings import Settings


def make_engine(settings: Settings) -> Engine:
    """Create the engine lazily; no file is touched until the first connection."""
    url = settings.sqlalchemy_url()
    if not url.startswith("sqlite"):
        return create_engine(url)
    engine = create_engine(url, connect_args={"check_same_thread": False})
    event.listen(engine, "connect", _sqlite_pragmas)
    return engine


def _sqlite_pragmas(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
