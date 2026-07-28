"""Shared pytest fixtures.

Sets a dedicated on-disk SQLite file for the test session (kept separate
from the app's normal leadflow.db) and guarantees GROQ_API_KEY starts unset
so tests default to the mock AI path unless a test opts into monkeypatching.
"""
import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).parent / "test_leadflow.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"
os.environ["GROQ_API_KEY"] = ""  # force mock AI path unless a test opts in

import pytest


@pytest.fixture(autouse=True, scope="session")
def _cleanup_test_db():
    yield
    from backend.database import engine

    engine.dispose()
    if TEST_DB_PATH.exists():
        try:
            TEST_DB_PATH.unlink()
        except PermissionError:
            pass  # Windows can briefly hold the file handle; not worth failing the suite over
