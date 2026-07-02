"""Core DataSource implementation backed by OANDA v20 pricing APIs."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any, cast

from core import Candle, CurrencyPair, DataSource, Tick

from oanda.config import OandaSettings
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
            response = ensure_success(
                self.gateway.get_instrument_prices(
                    oanda_instrument,
                    **{
                        "from": self._format_time(start_at),
                        "to": self._format_time(end_at),
                    },
                ),
                200,
            )
        prices = cast(Iterable[Any], self._body_get(response.body, "prices", ()) or ())
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
        response = ensure_success(
            self.gateway.get_account_prices(
                self.account_id,
                instruments=",".join(
                    OandaInstrumentMapper.to_oanda(instrument) for instrument in instruments
                ),
                since=self._format_time(since),
                includeUnitsAvailable=include_units_available,
                includeHomeConversions=include_home_conversions,
            ),
            200,
        )
        prices = cast(Iterable[Any], self._body_get(response.body, "prices", ()) or ())
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
            self.gateway.get_account_candles(
                self.account_id,
                OandaInstrumentMapper.to_oanda(instrument),
                {
                    "price": "M",
                    "granularity": granularity,
                    "from": self._format_time(start_at),
                    "to": self._format_time(end_at),
                },
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
        response = self.gateway.stream_account_prices(
            self.account_id,
            instruments=oanda_instruments,
            snapshot=snapshot,
        )
        for part_type, value in response.parts():
            if part_type.endswith("PricingHeartbeat"):
                continue
            yield self.mapper.tick_from_price(value)

    def stream_ticks(
        self,
        *,
        instruments: Iterable[CurrencyPair],
        snapshot: bool = True,
    ) -> Iterable[Tick]:
        """Yield live OANDA pricing stream updates as Core ticks."""
        return self.stream_prices(instruments=instruments, snapshot=snapshot)

    def close(self) -> None:
        """Close the underlying HTTP session when available."""
        close = getattr(self.gateway.opener, "close", None)
        if close is not None:
            close()

    def _format_time(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return self.gateway.datetime_to_str(value)

    @staticmethod
    def _body_get(body: object, key: str, default: object = None) -> object:
        if isinstance(body, Mapping):
            return body.get(key, default)
        return getattr(body, key, default)
