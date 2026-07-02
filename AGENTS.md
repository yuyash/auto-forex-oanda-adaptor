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

## Compatibility Policy

- Do not preserve backward compatibility in this package at this stage.
- Do not add compatibility aliases, deprecated wrappers, legacy shims, or
  duplicate old/new APIs.
- When an API changes, update all call sites and tests to the new API and remove
  the old implementation outright.

## Type Policy

- Prefer domain objects, enums, and structured models over accepting both an
  object and its serialized `str` form.
- Do not type public or internal APIs as `SomeObject | str` unless the function
  is explicitly a parser/factory at a serialization boundary, or the value is
  inherently textual such as an external ID, file path, protocol field, or log
  field.
- When removing `str` inputs, update all call sites and tests to construct the
  object before calling the API.

## Commands

```bash
uv sync
uv run ruff check .
uv run ruff format .
uv run ty check
uv run pytest
```
