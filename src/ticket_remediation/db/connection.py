import sqlite3
from importlib import resources
from pathlib import Path

# Columns added to remediation_runs after its initial release. CREATE TABLE IF NOT EXISTS is a
# no-op against an already-existing table, so pre-existing local DBs need these backfilled.
_REMEDIATION_RUNS_ADDED_COLUMNS = (
    ("failure_count", "INTEGER NOT NULL DEFAULT 0"),
    ("stage", "TEXT"),
)


def _apply_pending_migrations(conn: sqlite3.Connection) -> None:
    existing_columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(remediation_runs)").fetchall()
    }
    for column_name, column_ddl in _REMEDIATION_RUNS_ADDED_COLUMNS:
        if column_name not in existing_columns:
            conn.execute(f"ALTER TABLE remediation_runs ADD COLUMN {column_name} {column_ddl}")
    conn.commit()


def get_connection(db_path: Path | str) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    schema_sql = resources.files("ticket_remediation.db").joinpath("schema.sql").read_text()
    conn.executescript(schema_sql)
    _apply_pending_migrations(conn)
    return conn
