"""Shared fixtures and helpers for the test suite."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure the project root is on sys.path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Force every test to use a temporary SQLite database."""
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DB_PATH", str(db_file))
    yield
    # Cleanup happens automatically via tmp_path


@pytest.fixture()
def client():
    """Return a TestClient for the FastAPI app."""
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)
