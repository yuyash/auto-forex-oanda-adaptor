# Oanda Package Guide

`oanda` is the AutoForexV2 OANDA adapter library.

## Responsibilities

- Own all direct OANDA API communication.
- Adapt OANDA `v20` objects into internal AutoForex-friendly shapes.
- Own OANDA-specific settings and retry behavior.

## Boundaries

- Do not place core trading strategy logic here; put it in `core`.
- Do not expose web endpoints or gRPC services here.
- Do not let other packages call OANDA directly when this package can provide a
  focused adapter.

## Commands

```bash
uv sync
uv run ruff check .
uv run ruff format .
uv run ty check
uv run pytest
```
