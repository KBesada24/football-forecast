import os
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url

from src.core.config import Settings

BACKEND_DIR = Path(__file__).parents[1]
test_database_url = os.getenv("TEST_DATABASE_URL") or Settings().test_database_url  # type: ignore[call-arg]
if not test_database_url:
    raise RuntimeError("TEST_DATABASE_URL is required to run the backend test suite")
test_url = make_url(test_database_url)
app_url = make_url(Settings().database_url)  # type: ignore[call-arg]
if (
    test_url.get_backend_name() != "postgresql"
    or not (test_url.database or "").endswith("_test")
    # Compare names only: host aliases and default ports make endpoint equality unreliable.
    or test_url.database == app_url.database
):
    raise RuntimeError("Tests require a separate PostgreSQL database with a name ending in _test")
os.environ["DATABASE_URL"] = test_database_url


@pytest.fixture(scope="session")
def migrate_test_database() -> Generator[None, None, None]:
    alembic_config = Config(BACKEND_DIR / "alembic.ini")
    alembic_config.set_main_option("sqlalchemy.url", test_database_url.replace("%", "%%"))
    command.upgrade(alembic_config, "head")
    yield
