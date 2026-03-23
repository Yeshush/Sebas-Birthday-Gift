"""Integration tests for the FastAPI server."""
import json
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def client():
    from jobscraper.db import Base, get_db
    from jobscraper.server import app

    test_engine = create_async_engine(TEST_DB_URL)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    TestSession = async_sessionmaker(test_engine, expire_on_commit=False)

    async def override_get_db():
        async with TestSession() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest.mark.asyncio
async def test_register_and_login(client):
    r = await client.post("/api/register", json={"username": "testuser", "password": "pw123"})
    assert r.status_code == 201
    assert "access_token" in r.json()

    r2 = await client.post("/api/login", json={"username": "testuser", "password": "pw123"})
    assert r2.status_code == 200
    assert "access_token" in r2.json()
    assert r2.json()["username"] == "testuser"


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    await client.post("/api/register", json={"username": "u2", "password": "right"})
    r = await client.post("/api/login", json={"username": "u2", "password": "wrong"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_register_duplicate_username(client):
    await client.post("/api/register", json={"username": "u3", "password": "pw"})
    r = await client.post("/api/register", json={"username": "u3", "password": "pw"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_me_requires_auth(client):
    r = await client.get("/api/me", headers={"Authorization": "Bearer invalid"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_profile(client):
    r = await client.post("/api/register", json={"username": "me_user", "password": "pw"})
    token = r.json()["access_token"]
    r2 = await client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200
    body = r2.json()
    assert body["username"] == "me_user"
    assert "profile" in body
    assert isinstance(body["profile"]["interests"], list)
    assert isinstance(body["profile"]["min_workload"], int)


@pytest.mark.asyncio
async def test_history_empty(client):
    r = await client.post("/api/register", json={"username": "hist_user", "password": "pw"})
    token = r.json()["access_token"]
    r2 = await client.get("/api/history", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200
    assert r2.json() == []


@pytest.mark.asyncio
async def test_history_detail_not_found(client):
    r = await client.post("/api/register", json={"username": "hd_user", "password": "pw"})
    token = r.json()["access_token"]
    r2 = await client.get("/api/history/9999", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 404


@pytest.mark.asyncio
async def test_history_detail_returns_results_field(client):
    """history/{id} must return a 'results' key (not 'jobs') — matches Dashboard.jsx line 60."""
    from jobscraper.db import JobRow, SearchHistoryRow, UserRow
    from jobscraper.db import get_db
    from jobscraper.server import app

    r = await client.post("/api/register", json={"username": "detail_user", "password": "pw"})
    token = r.json()["access_token"]

    override = app.dependency_overrides[get_db]
    async for session in override():
        from sqlalchemy import select
        result = await session.execute(select(UserRow).where(UserRow.username == "detail_user"))
        user = result.scalar_one()
        hist = SearchHistoryRow(user_id=user.id, location="winterthur",
                                total_count=1, kept_count=1, easy_count=0)
        session.add(hist)
        await session.flush()
        session.add(JobRow(
            search_id=hist.id, uuid="x", title="Verkäufer", company="Migros",
            company_clean="Migros", location="Winterthur", workload="80-100%",
            easy_apply=False, url="https://jobs.ch/x", category="retail",
        ))
        await session.commit()
        hist_id = hist.id
        break

    r2 = await client.get(f"/api/history/{hist_id}", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200
    body = r2.json()
    assert "results" in body, "Response must use 'results' key to match frontend"
    assert len(body["results"]) == 1
    assert body["results"][0]["link"] is not None   # url → link mapping
