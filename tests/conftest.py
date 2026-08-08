import sqlite3
from pathlib import Path

import pytest

from ticket_remediation.db.connection import get_connection

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def db_conn(tmp_path) -> sqlite3.Connection:
    return get_connection(tmp_path / "state.db")
