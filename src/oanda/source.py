"""Core DataSource implementation backed by OANDA v20 pricing APIs."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from core import Candle, CurrencyPair, DataSource, Tick

from oanda.config import OandaEnvironment, OandaSettings
from oanda.errors import ensure_success
from oanda.gateway import OandaGateway
from oanda.mappers import OandaInstrumentMapper, OandaMarketDataMapper


class OandaDataSource(DataSource):
    """Market data source backed by OANDA v20."""

    def __init__(
        self,
        *,
        account_id: str,
        gateway: OandaGateway,
        mapper: OandaMarketDataMapper | None = None,
    ) -> None:
        self.account_id = account_id
        self.gateway = gateway
        self.mapper = mapper or OandaMarketDataMapper()

    @classmethod
    def from_settings(cls, settings: OandaSettings) -> OandaDataSource:
        """Create an OANDA data source from settings."""
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
    ) -> OandaDataSource:
        """Create an OANDA data source directly from account ID and token."""
        return cls(
            account_id=account_id,
            gateway=OandaGateway.from_credentials(
                access_token=access_token,
                environment=environment,
                hostname=hostname,
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

    def _raw_ticks(
        self,
        *,
        instrument: CurrencyPair,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> Iterable[Tick]:
        """Yield OANDA prices as Core ticks (sampling applied by ``ticks``)."""
        oanda_instrument = OandaInstrumentMapper.to_oanda(instrument)
        if start_at is None and end_at is None:
            response = ensure_success(
                self.gateway.get_account_prices(
                    self.account_id,
                    instruments=oanda_instrument,
                ),
                200,
            )
        else:
            response = ensure_success(
                self.gateway.get_instrument_prices(
                    oanda_instrument,
                    fromTime=self._format_time(start_at),
                    toTime=self._format_time(end_at),
                ),
                200,
            )
        prices = getattr(response, "body", {}).get("prices", ())
        return self.mapper.ticks_from_prices(prices)

    def candles(
        self,
        *,
        instrument: CurrencyPair,
        granularity: str,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> Iterable[Candle]:
        """Yield OANDA candlesticks as Core candles."""
        response = ensure_success(
            self.gateway.get_instrument_candles(
                OandaInstrumentMapper.to_oanda(instrument),
                price="M",
                granularity=granularity,
                fromTime=self._format_time(start_at),
                toTime=self._format_time(end_at),
            ),
            200,
        )
        return self.mapper.candles_from_response(
            response,
            instrument=instrument,
            granularity=granularity,
        )

    def stream_ticks(
        self,
        *,
        instruments: Iterable[CurrencyPair],
        snapshot: bool = True,
    ) -> Iterable[Tick]:
        """Yield live OANDA pricing stream updates as Core ticks."""
        oanda_instruments = ",".join(OandaInstrumentMapper.to_oanda(item) for item in instruments)
        response = self.gateway.stream_account_prices(
            self.account_id,
            instruments=oanda_instruments,
            snapshot=snapshot,
        )
        for part_type, value in response.parts():
            if part_type.endswith("PricingHeartbeat"):
                continue
            yield self.mapper.tick_from_price(value)

    def close(self) -> None:
        """Close the underlying HTTP session when available."""
        session = getattr(self.gateway.context, "_session", None)
        if session is not None:
            session.close()

    def _format_time(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return self.gateway.datetime_to_str(value)
