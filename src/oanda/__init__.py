"""OANDA v20 adapter package for AutoForexV2."""

from importlib.metadata import version

from oanda.broker import OandaBroker
from oanda.config import OandaEnvironment, OandaSettings
from oanda.errors import (
    OandaAdapterError,
    OandaApiError,
    OandaAuthenticationError,
    OandaAuthorizationError,
    OandaBadRequestError,
    OandaClientError,
    OandaConnectionError,
    OandaNotFoundError,
    OandaRateLimitError,
    OandaRetryableApiError,
    OandaServerError,
    OandaTimeoutError,
    OandaTransportError,
)
from oanda.gateway import OandaGateway, OandaRetryPolicy
from oanda.mappers import (
    OandaAccountMapper,
    OandaInstrumentMapper,
    OandaMarketDataMapper,
    OandaOrderMapper,
    OandaPositionMapper,
)
from oanda.source import OandaDataSource

__all__ = [
    "OandaAccountMapper",
    "OandaAdapterError",
    "OandaApiError",
    "OandaAuthenticationError",
    "OandaAuthorizationError",
    "OandaBadRequestError",
    "OandaBroker",
    "OandaClientError",
    "OandaConnectionError",
    "OandaDataSource",
    "OandaEnvironment",
    "OandaGateway",
    "OandaInstrumentMapper",
    "OandaMarketDataMapper",
    "OandaNotFoundError",
    "OandaOrderMapper",
    "OandaPositionMapper",
    "OandaRateLimitError",
    "OandaRetryPolicy",
    "OandaRetryableApiError",
    "OandaServerError",
    "OandaSettings",
    "OandaTimeoutError",
    "OandaTransportError",
    "__version__",
]

__version__ = version("oanda")
