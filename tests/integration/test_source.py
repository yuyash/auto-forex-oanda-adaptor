from __future__ import annotations

from core import CandleGranularity, CurrencyPair, Money

from oanda.source import OandaDataSource
from tests.integration.fakes import IntegrationGateway


class TestSource:
    def test_data_source_integrates_gateway_and_market_data_mapper_without_http(self) -> None:
        gateway = IntegrationGateway()
        source = OandaDataSource(
            account_id="001",
            pricing=gateway.pricing,
            time_formatter=gateway.transport,
            session=gateway.transport,
        )

        prices = tuple(source.prices(instruments=(CurrencyPair.of("USD_JPY"),)))
        candles = tuple(
            source.candles(
                instrument=CurrencyPair.of("USD_JPY"),
                granularity=CandleGranularity.MINUTE_1,
            )
        )

        assert prices[0].bid == Money.of("150.10", "JPY")
        assert candles[0].close == Money.of("150.10", "JPY")
