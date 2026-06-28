# oanda

OANDA v20 adapter for AutoForexV2.

## Components

- `OandaGateway`: thin wrapper for the OANDA v20 API surface.
- `OandaBroker`: Core `Broker` implementation.
- `OandaDataSource`: Core `DataSource` implementation for prices and candles.
- `OandaSettings`: environment-backed settings.

## Environment

```bash
OANDA_ACCOUNT_ID=...
OANDA_ACCESS_TOKEN=...
OANDA_ENVIRONMENT=practice
```

## Usage

```python
from oanda import OandaBroker, OandaDataSource, OandaSettings

settings = OandaSettings()
broker = OandaBroker.from_settings(settings)
source = OandaDataSource.from_settings(settings)

broker = OandaBroker.from_credentials(
    account_id="...",
    access_token="...",
)
```

## Setup

```bash
uv sync
```

## Development

```bash
uv run ruff check .
uv run ruff format .
uv run ty check
uv run pytest
```
