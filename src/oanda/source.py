"""Core DataSource implementation backed by OANDA v20 pricing APIs."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any, Protocol, cast

from core import Candle, CandleGranularity, CurrencyPair, DataSource, Tick

import oanda.models as om
from oanda.config import OandaSettings
from oanda.errors import OandaResponsePolicy
from oanda.gateway import OandaGateway
from oanda.mappers import OandaInstrumentMapper, OandaMarketDataMapper
from oanda.payload import OandaPayload as payload


class OandaPricingClient(Protocol):
    """OANDA pricing endpoint methods required by the data source."""

    def get_instrument_prices(self, instrument: str, **kwargs: Any) -> Any: ...
    def get_account_prices(self, account_id: str, request: Any = None, **kwargs: Any) -> Any: ...
    def get_account_candles(
        self,
        account_id: str,
        instrument: str,
        request: Any = None,
        **kwargs: Any,
    ) -> Any: ...
    def stream_account_prices(self, account_id: str, request: Any = None, **kwargs: Any) -> Any: ...


class OandaTimeFormatter(Protocol):
    """Formats datetimes for OANDA query parameters."""

    def datetime_to_str(self, value: Any) -> str: ...


class OandaSession(Protocol):
    """Closable OANDA session dependency."""

    opener: Any


class OandaDataSource(DataSource):
    """Market data source backed by OANDA v20."""

    def __init__(
        self,
        *,
        account_id: str,
        pricing: OandaPricingClient,
        time_formatter: OandaTimeFormatter,
        session: OandaSession | None = None,
        mapper: OandaMarketDataMapper | None = None,
    ) -> None:
        self.account_id = account_id
        self.pricing = pricing
        self.time_formatter = time_formatter
        self.session = session
        self.mapper = mapper or OandaMarketDataMapper()

    @classmethod
    def from_settings(cls, settings: OandaSettings) -> OandaDataSource:
        """Create an OANDA data source from settings."""
        gateway = OandaGateway.from_settings(settings)
        return cls(
            account_id=settings.account_id,
            pricing=gateway.pricing,
            time_formatter=gateway.transport,
            session=gateway.transport,
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
            return self.prices(instruments=(instrument,))
        else:
            response = OandaResponsePolicy.ensure_success(
                self.pricing.get_instrument_prices(
                    oanda_instrument,
                    **{
                        "from": self.format_time(start_at),
                        "to": self.format_time(end_at),
                    },
                ),
                200,
            )
        prices = cast(Iterable[Any], payload.get(response.body, "prices", ()) or ())
        return self.mapper.ticks_from_prices(prices)

    def prices(
        self,
        *,
        instruments: Iterable[CurrencyPair],
        since: datetime | None = None,
        include_units_available: bool = False,
        include_home_conversions: bool = False,
    ) -> Iterable[Tick]:
        """Return latest OANDA prices for one or more instruments."""
        response = OandaResponsePolicy.ensure_success(
            self.pricing.get_account_prices(
                self.account_id,
                om.PricingRequest.model_validate(
                    {
                        "instruments": tuple(
                            OandaInstrumentMapper.to_oanda(instrument) for instrument in instruments
                        ),
                        "since": self.format_time(since),
                        "includeUnitsAvailable": include_units_available,
                        "includeHomeConversions": include_home_conversions,
                    }
                ),
            ),
            200,
        )
        prices = cast(Iterable[Any], payload.get(response.body, "prices", ()) or ())
        return self.mapper.ticks_from_prices(prices)

    def candles(
        self,
        *,
        instrument: CurrencyPair,
        granularity: CandleGranularity,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> Iterable[Candle]:
        """Yield OANDA candlesticks as Core candles."""
        response = OandaResponsePolicy.ensure_success(
            self.pricing.get_account_candles(
                self.account_id,
                OandaInstrumentMapper.to_oanda(instrument),
                om.AccountCandlesRequest.model_validate(
                    {
                        "price": "M",
                        "granularity": granularity.value,
                        "from": self.format_time(start_at),
                        "to": self.format_time(end_at),
                    }
                ),
            ),
            200,
        )
        return self.mapper.candles_from_response(
            response,
            instrument=instrument,
            granularity=granularity,
        )

    def stream_prices(
        self,
        *,
        instruments: Iterable[CurrencyPair],
        snapshot: bool = True,
    ) -> Iterable[Tick]:
        """Yield live OANDA pricing stream updates as Core ticks."""
        oanda_instruments = ",".join(OandaInstrumentMapper.to_oanda(item) for item in instruments)
        response = self.pricing.stream_account_prices(
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
        if self.session is None:
            return
        close = getattr(self.session.opener, "close", None)
        if close is not None:
            close()

    def format_time(self, value: datetime | None) -> str | None:
        """Format an optional datetime for OANDA query parameters."""
        if value is None:
            return None
        return self.time_formatter.datetime_to_str(value)
