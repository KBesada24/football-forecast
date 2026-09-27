import asyncio

import pytest
from httpx import ASGITransport, AsyncClient, Response

from src.main import app


async def get(path: str) -> Response:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


def test_liveness() -> None:
    response = asyncio.run(get("/api/v1/health"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.usefixtures("migrate_test_database")
def test_database_readiness() -> None:
    response = asyncio.run(get("/api/v1/health/ready"))

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "connected"}
