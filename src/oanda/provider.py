"""OANDA provider service bundle."""

from __future__ import annotations

from typing import cast

from core import TradingProvider

from oanda.accounts import OandaAccountManager
from oanda.broker import OandaBroker
from oanda.config import OandaSettings
from oanda.constants import OANDA_PROVIDER
from oanda.gateway import OandaGateway
from oanda.source import OandaDataSource


class OandaProvider(TradingProvider):
    """Bundle OANDA account, broker, and market-data services."""

    _account_id: str
    _gateway: OandaGateway
    __slots__ = ("_account_id", "_gateway")

    def __init__(self, *, account_id: str, gateway: OandaGateway) -> None:
        object.__setattr__(self, "_account_id", account_id)
        object.__setattr__(self, "_gateway", gateway)
        super().__init__(
            provider=OANDA_PROVIDER,
            account_manager=OandaAccountManager(accounts=gateway.accounts),
            broker=OandaBroker(account_id=account_id, gateway=gateway),
            data=OandaDataSource(
                account_id=account_id,
                pricing=gateway.pricing,
                time_formatter=gateway.transport,
                session=gateway.transport,
            ),
        )

    @property
    def account_id(self) -> str:
        """Return the configured OANDA account ID."""
        return self._account_id

    @property
    def gateway(self) -> OandaGateway:
        """Return the shared OANDA gateway."""
        return self._gateway

    @property
    def account_manager(self) -> OandaAccountManager:
        """Return the OANDA account service."""
        return cast(OandaAccountManager, super().account_manager)

    @property
    def accounts(self) -> OandaAccountManager:
        """Alias for OANDA account-related operations."""
        return self.account_manager

    @property
    def broker(self) -> OandaBroker:
        """Return the OANDA broker service."""
        return cast(OandaBroker, super().broker)

    @property
    def data(self) -> OandaDataSource:
        """Return the OANDA market-data service."""
        return cast(OandaDataSource, super().data)

    @classmethod
    def from_settings(cls, settings: OandaSettings) -> OandaProvider:
        """Create an OANDA provider bundle from settings."""
        return cls(
            account_id=settings.account_id,
            gateway=OandaGateway.from_settings(settings),
        )
