from fastapi import FastAPI, Query

from mock_servers.common.state import mount_debug_routes

from .generator import generate_tickets

app = FastAPI(title="ServiceNow AVIT Mock")

_tables: dict[str, list[dict]] = {}


def _reset() -> None:
    _tables.clear()


mount_debug_routes(app, _reset)


@app.get("/api/now/table/{table}")
def list_table(
    table: str,
    sysparm_query: str | None = Query(default=None),
    sysparm_limit: int = Query(default=50),
) -> dict:
    if table not in _tables:
        _tables[table] = generate_tickets(count=8)
    rows = _tables[table]
    if sysparm_query and ">=" in sysparm_query:
        field, _, value = sysparm_query.partition(">=")
        rows = [r for r in rows if str(r.get(field.strip(), "")) >= value.strip()]
    return {"result": rows[:sysparm_limit]}


@app.post("/_debug/seed")
def seed(
    table: str,
    count: int = 8,
    seed: int | None = None,
    demo_relevant_only: bool = False,
) -> dict:
    """Mock-only: force-regenerate a table's synthetic findings for a reproducible demo run."""
    _tables[table] = generate_tickets(count=count, seed=seed, demo_relevant_only=demo_relevant_only)
    return {"table": table, "count": len(_tables[table])}
