"""Shared helpers for OANDA payload access and conversion."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Any

from core import Metadata
from core.clock import local_timezone


def body(response: Any) -> Any:
    """Return a response body object or an empty mapping."""
    return getattr(response, "body", None) or {}


def metadata(data: Any) -> Metadata:
    """Convert an OANDA payload object into Core metadata."""
    if data is None:
        return Metadata.model_validate({})
    if hasattr(data, "model_dump"):
        return Metadata.model_validate(
            data.model_dump(mode="json", by_alias=True, exclude_none=True)
        )
    if isinstance(data, Mapping):
        return Metadata.model_validate(dict(data))
    values = {
        key: value
        for key in dir(data)
        if not key.startswith("_") and not callable(value := getattr(data, key))
    }
    return Metadata.model_validate(values)


def first(data: Any, *keys: str) -> Any:
    """Return the first non-None value found by OANDA alias-aware lookup."""
    for key in keys:
        value = get(data, key)
        if value is not None:
            return value
    return None


def get(data: Any, key: str, default: Any = None) -> Any:
    """Read an OANDA field from mappings, pydantic models, or v20 objects."""
    if data is None:
        return default
    if isinstance(data, Mapping):
        if key in data:
            return data[key]
        return data.get(snake(key), default)
    if hasattr(data, key):
        return getattr(data, key)
    return getattr(data, snake(key), default)


def snake(name: str) -> str:
    """Convert an OANDA camelCase/PascalCase field name to snake_case."""
    value = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    return value.lower()


def decimal(value: Any) -> Decimal:
    """Convert an OANDA decimal-like value."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def parse_time(value: Any) -> datetime:
    """Parse an OANDA timestamp without inventing missing time values."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=local_timezone())
        return value
    if value is None:
        msg = "OANDA timestamp is required"
        raise ValueError(msg)

    text = str(value)
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    if "." in text:
        prefix, suffix = text.split(".", 1)
        fraction = suffix
        timezone = ""
        for separator in ("+", "-"):
            if separator in suffix:
                fraction, timezone = suffix.split(separator, 1)
                timezone = f"{separator}{timezone}"
                break
        text = f"{prefix}.{fraction[:6].ljust(6, '0')}{timezone}"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=local_timezone())
    return parsed


def average_candle_data(bid: Any, ask: Any) -> dict[str, Decimal]:
    """Average OANDA bid and ask candle data into one OHLC mapping."""
    if bid is None or ask is None:
        msg = "OANDA candle must include mid data or both bid and ask data"
        raise ValueError(msg)
    return {
        key: (decimal(get(bid, key)) + decimal(get(ask, key))) / 2 for key in ("o", "h", "l", "c")
    }


def clean(values: Mapping[str, object]) -> dict[str, object]:
    """Drop OANDA request values that should not be sent."""
    return {key: value for key, value in values.items() if value is not None}


def client_extensions(
    *,
    client_id: str | None,
    tag: str | None,
    comment: str | None,
) -> dict[str, dict[str, str]]:
    """Build an OANDA clientExtensions request body."""
    extensions = clean({"id": client_id, "tag": tag, "comment": comment})
    return {"clientExtensions": {key: str(value) for key, value in extensions.items()}}
