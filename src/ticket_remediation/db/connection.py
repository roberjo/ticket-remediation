import sqlite3
from importlib import resources
from pathlib import Path


def get_connection(db_path: Path | str) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    schema_sql = resources.files("ticket_remediation.db").joinpath("schema.sql").read_text()
    conn.executescript(schema_sql)
    return conn
