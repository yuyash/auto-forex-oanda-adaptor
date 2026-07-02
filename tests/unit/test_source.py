from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

from core import CurrencyPair, Money, Tick

from oanda.source import OandaDataSource
from tests.support import FakeResponse

USD_JPY = CurrencyPair.of("USD_JPY")


class StreamResponseFake:
    def parts(self) -> tuple[tuple[str, object], ...]:
        return (
            ("PricingHeartbeat", SimpleNamespace()),
            ("ClientPrice", SimpleNamespace(instrument="USD_JPY")),
        )


class TestSource:
    def test_data_source_prices_uses_account_pricing_endpoint(self) -> None:
        gateway = Mock()
        mapper = Mock()
        tick = Tick(
            instrument=USD_JPY,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            bid=Money.of("150.10", "JPY"),
            ask=Money.of("150.12", "JPY"),
        )
        gateway.get_account_prices.return_value = FakeResponse(200, {"prices": ["price"]})
        gateway.datetime_to_str.return_value = "2026-01-01T00:00:00Z"
        mapper.ticks_from_prices.return_value = (tick,)
        source = OandaDataSource(account_id="001", gateway=gateway, mapper=mapper)

        result = tuple(
            source.prices(
                instruments=(USD_JPY,),
                since=datetime(2026, 1, 1, tzinfo=UTC),
                include_units_available=True,
                include_home_conversions=True,
            )
        )

        assert result == (tick,)
        gateway.get_account_prices.assert_called_once_with(
            "001",
            instruments="USD_JPY",
            since="2026-01-01T00:00:00Z",
            includeUnitsAvailable=True,
            includeHomeConversions=True,
        )
        mapper.ticks_from_prices.assert_called_once_with(["price"])

    def test_data_source_candles_uses_account_candles_endpoint(self) -> None:
        gateway = Mock()
        mapper = Mock()
        gateway.get_account_candles.return_value = FakeResponse(200, {"candles": ["candle"]})
        mapper.candles_from_response.return_value = ("mapped-candle",)
        source = OandaDataSource(account_id="001", gateway=gateway, mapper=mapper)

        assert tuple(source.candles(instrument=USD_JPY, granularity="M1")) == ("mapped-candle",)
        gateway.get_account_candles.assert_called_once_with(
            "001",
            "USD_JPY",
            {"price": "M", "granularity": "M1", "from": None, "to": None},
        )

    def test_data_source_stream_prices_yields_mapped_non_heartbeat_parts(self) -> None:
        gateway = Mock()
        mapper = Mock()
        tick = Tick(
            instrument=USD_JPY,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            bid=Money.of("150.10", "JPY"),
            ask=Money.of("150.12", "JPY"),
        )
        gateway.stream_account_prices.return_value = StreamResponseFake()
        mapper.tick_from_price.return_value = tick
        source = OandaDataSource(account_id="001", gateway=gateway, mapper=mapper)

        assert tuple(source.stream_ticks(instruments=(USD_JPY,), snapshot=False)) == (tick,)
        gateway.stream_account_prices.assert_called_once_with(
            "001",
            instruments="USD_JPY",
            snapshot=False,
        )

    def test_data_source_close_closes_gateway_opener(self) -> None:
        opener = Mock()
        gateway = Mock()
        gateway.opener = opener
        source = OandaDataSource(account_id="001", gateway=gateway, mapper=Mock())

        source.close()

        opener.close.assert_called_once_with()
