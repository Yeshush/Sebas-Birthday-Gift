"""SQLAlchemy 2.0 async models for JobScraper."""
from __future__ import annotations

import json
import os
from collections.abc import AsyncGenerator

from dotenv import load_dotenv
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Index,
    Integer, String, Text,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql import func

load_dotenv()

_raw_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./jobscraper.db")
if _raw_url.startswith("postgres://"):
    DATABASE_URL = _raw_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif _raw_url.startswith("postgresql://"):
    DATABASE_URL = _raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
else:
    DATABASE_URL = _raw_url

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class UserRow(Base):
    __tablename__ = "users"
    id            = Column(Integer, primary_key=True)
    username      = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at    = Column(DateTime, server_default=func.now())


class ProfileRow(Base):
    __tablename__ = "profiles"
    id                 = Column(Integer, primary_key=True)
    user_id            = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    education_level    = Column(String(50), nullable=True)
    min_workload       = Column(Integer, nullable=False, default=80)
    interests          = Column(Text, nullable=True)
    allow_quereinstieg = Column(Boolean, nullable=False, default=True)

    def get_interests_list(self) -> list[str]:
        if self.interests:
            try:
                parsed = json.loads(self.interests)
                return parsed if isinstance(parsed, list) else []
            except (json.JSONDecodeError, TypeError):
                return []
        return []


class SearchHistoryRow(Base):
    __tablename__ = "search_history"
    __table_args__ = (Index("ix_search_history_user_id", "user_id"),)
    id          = Column(Integer, primary_key=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False)
    location    = Column(String(100), nullable=False)
    timestamp   = Column(DateTime, server_default=func.now())
    total_count = Column(Integer, nullable=True)
    kept_count  = Column(Integer, nullable=True)
    easy_count  = Column(Integer, nullable=True)


class JobRow(Base):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_search_id", "search_id"),)
    id            = Column(Integer, primary_key=True)
    search_id     = Column(Integer, ForeignKey("search_history.id", ondelete="CASCADE"), nullable=False)
    uuid          = Column(String(100))
    title         = Column(String(500))
    company       = Column(String(200))
    company_clean = Column(String(200))
    location      = Column(String(200))
    workload      = Column(String(100))
    contract_type = Column(String(100))
    published     = Column(String(100))
    is_promoted   = Column(Boolean)
    easy_apply    = Column(Boolean)
    url           = Column(Text)
    category      = Column(String(50))


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
