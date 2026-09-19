"""Declarative base and shared column helpers."""

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Stable constraint names are required for SQLite batch migrations.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def new_id() -> str:
    return str(uuid.uuid4())


def include_object(
    obj: Any, name: str | None, type_: str, reflected: bool, compare_to: Any
) -> bool:
    """Hide objects Alembic cannot model: the FTS5 table and its shadow tables (ADR-0008)."""
    return not (type_ == "table" and name is not None and name.startswith("chunks_fts"))


def as_utc(value: dt.datetime) -> dt.datetime:
    """SQLite returns naive datetimes; Ichnos always stores UTC, so attach the zone."""
    return value if value.tzinfo is not None else value.replace(tzinfo=dt.UTC)
