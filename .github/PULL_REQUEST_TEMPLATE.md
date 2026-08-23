## What changed and why

<!-- The "why" matters more than the "what" — the diff already shows what changed. -->

## Checklist

- [ ] `uv run ruff check .` / `uv run mypy src` pass
- [ ] `uv run pytest` and `uv run pytest -m contract` pass
- [ ] New behavior has a test (pipeline logic → a fake-based test; a connector → a respx or
      contract test)
- [ ] Docs updated if this changes configuration, an ADR-level decision, or the state model
      (`docs/architecture/`)
