import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///./test_patchpilot.sqlite3"
os.environ["SEED_DEMO_DATA"] = "false"
os.environ["AUTO_CREATE_SCHEMA"] = "true"
os.environ["PATCHPILOT_DEMO_MODE"] = "true"

from patchpilot.db.base import Base  # noqa: E402
from patchpilot.db.session import SessionLocal, engine  # noqa: E402
from patchpilot.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def pytest_sessionfinish(session, exitstatus):
    engine.dispose()
    path = Path("test_patchpilot.sqlite3")
    if path.exists():
        path.unlink()

