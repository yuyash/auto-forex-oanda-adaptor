"""OANDA v20 adapter package for AutoForexV2."""

from importlib.metadata import version

from oanda.accounts import OandaAccountManager
from oanda.broker import OandaBroker
from oanda.config import OandaEnvironment, OandaSettings
from oanda.domain import (
    OandaAccount,
    OandaAccountSummary,
    OandaOrder,
    OandaPosition,
    OandaTrade,
    OandaTransaction,
)
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
from oanda.models import OandaModel, OandaResponse
from oanda.provider import OandaProvider
from oanda.source import OandaDataSource

__all__ = [
    "OandaAccount",
    "OandaAccountManager",
    "OandaAccountMapper",
    "OandaAccountSummary",
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
    "OandaModel",
    "OandaNotFoundError",
    "OandaOrder",
    "OandaOrderMapper",
    "OandaPosition",
    "OandaPositionMapper",
    "OandaProvider",
    "OandaRateLimitError",
    "OandaResponse",
    "OandaRetryPolicy",
    "OandaRetryableApiError",
    "OandaServerError",
    "OandaSettings",
    "OandaTimeoutError",
    "OandaTrade",
    "OandaTransaction",
    "OandaTransportError",
    "__version__",
]

__version__ = version("oanda")
