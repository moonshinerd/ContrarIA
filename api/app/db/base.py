"""Base declarativa do SQLAlchemy. Classes ORM ficam em app/db/orm/."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
