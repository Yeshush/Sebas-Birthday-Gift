"""Tests for SQLAlchemy async models."""

import json
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from jobscraper.db import Base, UserRow, ProfileRow, SearchHistoryRow, JobRow

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_user(session):
    user = UserRow(username="alice", password_hash="hashed")
    session.add(user)
    await session.commit()
    assert user.id is not None


@pytest.mark.asyncio
async def test_create_profile_with_interests(session):
    user = UserRow(username="bob", password_hash="hashed")
    session.add(user)
    await session.flush()
    profile = ProfileRow(
        user_id=user.id,
        min_workload=80,
        interests=json.dumps(["verkauf", "lager"]),
        allow_quereinstieg=True,
    )
    session.add(profile)
    await session.commit()
    assert profile.get_interests_list() == ["verkauf", "lager"]


@pytest.mark.asyncio
async def test_profile_empty_interests(session):
    user = UserRow(username="carol", password_hash="hashed")
    session.add(user)
    await session.flush()
    profile = ProfileRow(user_id=user.id)
    session.add(profile)
    await session.commit()
    assert profile.get_interests_list() == []


@pytest.mark.asyncio
async def test_create_search_history(session):
    user = UserRow(username="dave", password_hash="hashed")
    session.add(user)
    await session.flush()
    history = SearchHistoryRow(
        user_id=user.id, location="winterthur",
        total_count=100, kept_count=10, easy_count=3,
    )
    session.add(history)
    await session.commit()
    assert history.id is not None


@pytest.mark.asyncio
async def test_create_job_row(session):
    user = UserRow(username="eve", password_hash="hashed")
    session.add(user)
    await session.flush()
    history = SearchHistoryRow(user_id=user.id, location="zurich")
    session.add(history)
    await session.flush()
    job = JobRow(
        search_id=history.id,
        uuid="abc-123",
        title="Verkäufer/in",
        company="Migros AG",
        easy_apply=True,
        url="https://www.jobs.ch/en/vacancies/detail/abc/",
    )
    session.add(job)
    await session.commit()
    assert job.id is not None
