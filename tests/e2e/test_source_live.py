from __future__ import annotations

from core import CurrencyPair, Tick

from oanda import OandaProvider


def test_live_data_source_prices_and_candles(
    oanda_provider: OandaProvider,
    e2e_instrument: CurrencyPair,
) -> None:
    prices = tuple(oanda_provider.data_source.prices(instruments=(e2e_instrument,)))
    candles = tuple(oanda_provider.data_source.candles(instrument=e2e_instrument, granularity="M1"))

    assert prices
    assert prices[0].instrument == e2e_instrument
    assert candles
    assert candles[0].instrument == e2e_instrument


def test_live_data_source_pricing_stream_snapshot(
    oanda_provider: OandaProvider,
    e2e_instrument: CurrencyPair,
) -> None:
    stream = oanda_provider.data_source.stream_ticks(
        instruments=(e2e_instrument,),
        snapshot=True,
    )
    tick = next(iter(stream))

    assert isinstance(tick, Tick)
    assert tick.instrument == e2e_instrument
