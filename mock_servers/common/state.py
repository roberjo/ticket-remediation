import itertools
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, FastAPI


class RecordStore:
    """Generic in-memory, id-keyed record store used for CRUD-style mocks (Jira)."""

    def __init__(self, id_prefix: str = "REC"):
        self._records: dict[str, dict[str, Any]] = {}
        self._counter = itertools.count(1)
        self._id_prefix = id_prefix

    def next_key(self) -> str:
        return f"{self._id_prefix}-{next(self._counter)}"

    def put(self, key: str, record: dict[str, Any]) -> None:
        self._records[key] = record

    def get(self, key: str) -> dict[str, Any] | None:
        return self._records.get(key)

    def delete(self, key: str) -> bool:
        return self._records.pop(key, None) is not None

    def all(self) -> list[dict[str, Any]]:
        return list(self._records.values())

    def reset(self) -> None:
        self._records.clear()
        self._counter = itertools.count(1)


def mount_debug_routes(app: FastAPI, reset_fn: Callable[[], None]) -> None:
    """Adds /_debug/reset — mock-only, never exists on a real ServiceNow/Jira instance.
    Lets tests and local dev clear state between runs without restarting the server."""
    router = APIRouter()

    @router.post("/_debug/reset")
    def reset() -> dict[str, str]:
        reset_fn()
        return {"status": "reset"}

    app.include_router(router)
