"""OANDA provider service bundle."""

from __future__ import annotations

from core import AccountProvider, TradingProvider

from oanda.accounts import OandaAccountManager
from oanda.broker import OandaBroker
from oanda.config import OandaEnvironment, OandaSettings
from oanda.gateway import OandaGateway
from oanda.source import OandaDataSource


class OandaProvider(TradingProvider):
    """Bundle OANDA account, broker, and market-data services."""

    __slots__ = ("account_id", "gateway")

    def __init__(self, *, account_id: str, gateway: OandaGateway) -> None:
        self.account_id = account_id
        self.gateway = gateway
        super().__init__(
            provider=AccountProvider.OANDA,
            account_manager=OandaAccountManager(gateway=gateway),
            broker=OandaBroker(account_id=account_id, gateway=gateway),
            data_source=OandaDataSource(account_id=account_id, gateway=gateway),
        )

    @classmethod
    def from_settings(cls, settings: OandaSettings) -> OandaProvider:
        """Create an OANDA provider bundle from settings."""
        return cls(
            account_id=settings.account_id,
            gateway=OandaGateway.from_settings(settings),
        )

    @classmethod
    def from_credentials(
        cls,
        *,
        account_id: str,
        access_token: str,
        environment: OandaEnvironment = OandaEnvironment.PRACTICE,
        hostname: str | None = None,
        stream_hostname: str | None = None,
        port: int = 443,
        ssl: bool = True,
        application: str = "AutoForexV2",
        stream_chunk_size: int = 512,
        stream_timeout: int = 60,
        poll_timeout: int = 10,
        retry_attempts: int = 3,
        retry_initial_seconds: float = 0.25,
        retry_max_seconds: float = 4.0,
        retry_multiplier: float = 2.0,
    ) -> OandaProvider:
        """Create an OANDA provider bundle directly from account ID and token."""
        return cls(
            account_id=account_id,
            gateway=OandaGateway.from_credentials(
                access_token=access_token,
                environment=environment,
                hostname=hostname,
                stream_hostname=stream_hostname,
                port=port,
                ssl=ssl,
                application=application,
                stream_chunk_size=stream_chunk_size,
                stream_timeout=stream_timeout,
                poll_timeout=poll_timeout,
                retry_attempts=retry_attempts,
                retry_initial_seconds=retry_initial_seconds,
                retry_max_seconds=retry_max_seconds,
                retry_multiplier=retry_multiplier,
            ),
        )
