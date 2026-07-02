"""OANDA provider service bundle."""

from __future__ import annotations

from core import TradingProvider

from oanda.accounts import OandaAccountManager
from oanda.broker import OandaBroker
from oanda.config import OandaSettings
from oanda.constants import OANDA_PROVIDER
from oanda.gateway import OandaGateway
from oanda.source import OandaDataSource


class OandaProvider(TradingProvider):
    """Bundle OANDA account, broker, and market-data services."""

    __slots__ = ("_account_id", "_gateway")

    def __init__(self, *, account_id: str, gateway: OandaGateway) -> None:
        self._account_id = account_id
        self._gateway = gateway
        super().__init__(
            provider=OANDA_PROVIDER,
            account_manager=OandaAccountManager(gateway=gateway),
            broker=OandaBroker(account_id=account_id, gateway=gateway),
            data=OandaDataSource(account_id=account_id, gateway=gateway),
        )

    @property
    def account_id(self) -> str:
        """Return the configured OANDA account ID."""
        return self._account_id

    @property
    def gateway(self) -> OandaGateway:
        """Return the shared OANDA gateway."""
        return self._gateway

    @classmethod
    def from_settings(cls, settings: OandaSettings) -> OandaProvider:
        """Create an OANDA provider bundle from settings."""
        return cls(
            account_id=settings.account_id,
            gateway=OandaGateway.from_settings(settings),
        )
