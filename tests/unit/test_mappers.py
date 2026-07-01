from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from core import CurrencyPair, Money, Order, OrderSide, OrderStatus, OrderType, PositionSide

from oanda.mappers import (
    OandaAccountMapper,
    OandaInstrumentMapper,
    OandaMarketDataMapper,
    OandaOrderMapper,
    OandaPositionMapper,
    OandaTradeMapper,
    OandaTransactionMapper,
)
from tests.support import FakeResponse, candle_namespace, price_namespace

USD_JPY = CurrencyPair.of("USD_JPY")


def test_instrument_mapper_converts_between_core_and_oanda_symbols() -> None:
    assert OandaInstrumentMapper.to_oanda(USD_JPY) == "USD_JPY"
    assert OandaInstrumentMapper.to_core("USD_JPY") == USD_JPY


def test_account_mapper_maps_properties_summary_and_currency() -> None:
    account = OandaAccountMapper.account_from_properties(
        SimpleNamespace(id="001", alias="primary", mt4AccountID=123, tags=("demo",))
    )
    response = FakeResponse(
        200,
        {
            "account": {
                "id": "001",
                "currency": "USD",
                "alias": "primary",
                "balance": "1000.00",
                "NAV": "1001.00",
                "marginUsed": "10.00",
                "marginAvailable": "991.00",
                "marginRate": "0.02",
                "createdTime": "2026-01-01T00:00:00.000000000Z",
            },
            "lastTransactionID": "10",
        },
    )
    summary = OandaAccountMapper.summary_from_response(response)

    assert account.id.value == "001"
    assert account.mt4_account_id == 123
    assert summary.balance == Money.of("1000.00", "USD")
    assert OandaAccountMapper.account_currency_from_response(response).code == "USD"


def test_order_mapper_builds_request_and_maps_fill_response() -> None:
    order = Order(
        instrument=USD_JPY,
        side=OrderSide.SELL,
        units=Decimal("1000"),
        order_type=OrderType.MARKET,
    )
    response = FakeResponse(
        201,
        {
            "orderCreateTransaction": SimpleNamespace(id="100"),
            "orderFillTransaction": SimpleNamespace(
                id="101",
                orderID="100",
                units="-1000",
                price="150.12",
            ),
            "lastTransactionID": "101",
            "relatedTransactionIDs": ("100", "101"),
        },
    )
    mapper = OandaOrderMapper()

    kwargs = mapper.order_kwargs(order)
    mapped = mapper.order_from_order_response(response, order)

    assert kwargs["units"] == "-1000"
    assert mapped.status == OrderStatus.FILLED
    assert mapped.filled_units == Decimal("1000")
    assert mapped.average_fill_price == Money.of("150.12", "JPY")


def test_position_trade_transaction_and_market_data_mappers() -> None:
    position_response = FakeResponse(
        200,
        {
            "positions": [
                SimpleNamespace(
                    instrument="USD_JPY",
                    long=SimpleNamespace(
                        units="1000",
                        averagePrice="150.10",
                        unrealizedPL="12.50",
                    ),
                    short=SimpleNamespace(units="0"),
                )
            ]
        },
    )
    trade_response = FakeResponse(
        200,
        {
            "trades": [
                SimpleNamespace(
                    id="200",
                    instrument="USD_JPY",
                    currentUnits="1000",
                    initialUnits="1000",
                    price="150.10",
                    openTime="2026-01-01T00:00:00.000000000Z",
                    state="OPEN",
                    unrealizedPL="12.50",
                    realizedPL="0.00",
                )
            ]
        },
    )
    transaction_response = FakeResponse(
        200,
        {
            "transactions": [
                SimpleNamespace(
                    id="300",
                    accountID="001",
                    type="ORDER_FILL",
                    instrument="USD_JPY",
                    orderID="100",
                    pl="1.25",
                )
            ]
        },
    )
    price_response = FakeResponse(200, {"prices": [price_namespace()]})
    candle_response = FakeResponse(200, {"candles": [candle_namespace()]})

    positions = OandaPositionMapper(account_currency="USD").positions_from_response(
        position_response
    )
    trades = OandaTradeMapper(account_currency="USD").trades_from_response(trade_response)
    transactions = OandaTransactionMapper(account_currency="USD").transactions_from_response(
        transaction_response
    )
    market_data = OandaMarketDataMapper()
    ticks = market_data.ticks_from_prices(price_response.body["prices"])
    candles = market_data.candles_from_response(
        candle_response,
        instrument=USD_JPY,
        granularity="M1",
    )

    assert positions[0].long is not None
    assert positions[0].long.side == PositionSide.LONG
    assert positions[0].long.unrealized_pl == Money.of("12.50", "USD")
    assert trades[0].id.value == "200"
    assert trades[0].unrealized_pl == Money.of("12.50", "USD")
    assert transactions[0].amount == Money.of("1.25", "USD")
    assert ticks[0].bid == Money.of("150.10", "JPY")
    assert candles[0].close == Money.of("150.10", "JPY")


def test_position_mapper_keeps_oanda_long_and_short_sides() -> None:
    response = FakeResponse(
        200,
        {
            "positions": [
                SimpleNamespace(
                    instrument="USD_JPY",
                    long=SimpleNamespace(
                        units="1000",
                        averagePrice="150.10",
                        unrealizedPL="12.50",
                    ),
                    short=SimpleNamespace(
                        units="-500",
                        averagePrice="150.20",
                        unrealizedPL="-3.25",
                    ),
                )
            ]
        },
    )

    positions = OandaPositionMapper(account_currency="USD").positions_from_response(response)

    assert positions[0].long is not None
    assert positions[0].short is not None
    assert positions[0].open_sides == (PositionSide.LONG, PositionSide.SHORT)
    assert positions[0].long.units == Decimal("1000")
    assert positions[0].short.units == Decimal("500")
