from __future__ import annotations

from core import CandleGranularity, CurrencyPair, Tick

from oanda import OandaProvider


class TestSourceLive:
    def test_live_data_source_prices_and_candles(
        self,
        oanda_provider: OandaProvider,
        e2e_instrument: CurrencyPair,
    ) -> None:
        prices = tuple(oanda_provider.data.prices(instruments=(e2e_instrument,)))
        candles = tuple(
            oanda_provider.data.candles(
                instrument=e2e_instrument,
                granularity=CandleGranularity.MINUTE_1,
            )
        )

        assert prices
        assert prices[0].instrument == e2e_instrument
        assert candles
        assert candles[0].instrument == e2e_instrument

    def test_live_data_source_pricing_stream_snapshot(
        self,
        oanda_provider: OandaProvider,
        e2e_instrument: CurrencyPair,
    ) -> None:
        stream = oanda_provider.data.stream_prices(
            instruments=(e2e_instrument,),
            snapshot=True,
        )
        tick = next(iter(stream))

        assert isinstance(tick, Tick)
        assert tick.instrument == e2e_instrument
