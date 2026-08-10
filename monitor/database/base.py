"""DeclarativeBase partilhada pelos modelos ORM."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
