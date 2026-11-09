"""Базовый декларативный класс SQLAlchemy для моделей приложения."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Общий DeclarativeBase, на котором регистрируются ORM-модели."""
    pass
