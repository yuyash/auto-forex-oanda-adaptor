from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import pytest
from core import (
    CurrencyPair,
    Money,
    OrderRequest,
    OrderRequestId,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionSide,
)

from oanda import OandaBroker, OandaDataSource, OandaGateway
from oanda.config import OandaEnvironment
from oanda.errors import OandaAuthenticationError
from oanda.gateway import OandaRetryPolicy
from oanda.mappers import OandaOrderMapper, OandaPositionMapper

USD_JPY = CurrencyPair.of("USD_JPY")


class FakeResponse:
    def __init__(self, status: int, body: dict[str, Any], reason: str = "OK") -> None:
        self.status = status
        self.body = body
        self.reason = reason


class FakeGateway:
    def __init__(self) -> None:
        self.market_orders: list[dict[str, Any]] = []
        self.close_position_calls: list[tuple[str, dict[str, Any]]] = []
        self.account_summary_calls = 0

    def get_account_summary(self, account_id: str) -> FakeResponse:
        _ = account_id
        self.account_summary_calls += 1
        return FakeResponse(200, {"account": SimpleNamespace(currency="USD")})

    def create_market_order(self, account_id: str, **kwargs: Any) -> FakeResponse:
        _ = account_id
        self.market_orders.append(kwargs)
        return FakeResponse(
            201,
            {
                "orderCreateTransaction": SimpleNamespace(id="100"),
                "orderFillTransaction": SimpleNamespace(
                    id="101",
                    orderID="100",
                    units=kwargs["units"],
                    price="150.12",
                ),
                "lastTransactionID": "101",
                "relatedTransactionIDs": ["100", "101"],
            },
            "Created",
        )

    def list_open_positions(self, account_id: str) -> FakeResponse:
        _ = account_id
        return FakeResponse(
            200,
            {
                "positions": [
                    SimpleNamespace(
                        instrument="USD_JPY",
                        long=SimpleNamespace(
                            units="1000",
                            averagePrice="150.10",
                            unrealizedPL="12.50",
                            tradeIDs=["200"],
                            pl="1.00",
                            resettablePL="1.00",
                            financing="0.00",
                        ),
                        short=SimpleNamespace(units="0"),
                    )
                ]
            },
        )

    def close_position(self, account_id: str, instrument: str, **kwargs: Any) -> FakeResponse:
        _ = account_id
        self.close_position_calls.append((instrument, kwargs))
        return FakeResponse(
            200,
            {
                "longOrderCreateTransaction": SimpleNamespace(id="102"),
                "longOrderFillTransaction": SimpleNamespace(
                    id="103",
                    orderID="102",
                    units="-250",
                    price="150.11",
                ),
            },
        )

    def get_account_prices(self, account_id: str, **kwargs: Any) -> FakeResponse:
        _ = account_id
        _ = kwargs
        return FakeResponse(
            200,
            {
                "prices": [
                    SimpleNamespace(
                        instrument="USD_JPY",
                        time="2026-01-01T00:00:00.000000000Z",
                        status="tradeable",
                        tradeable=True,
                        bids=[SimpleNamespace(price="150.10")],
                        asks=[SimpleNamespace(price="150.12")],
                        closeoutBid="150.09",
                        closeoutAsk="150.13",
                    )
                ]
            },
        )

    def get_instrument_candles(self, instrument: str, **kwargs: Any) -> FakeResponse:
        _ = instrument
        return FakeResponse(
            200,
            {
                "candles": [
                    SimpleNamespace(
                        time="2026-01-01T00:00:00.000000000Z",
                        mid=SimpleNamespace(
                            o="150.00",
                            h="150.20",
                            l="149.90",
                            c="150.10",
                        ),
                        volume=120,
                        complete=True,
                    )
                ],
                "granularity": kwargs["granularity"],
            },
        )

    def datetime_to_str(self, value: object) -> str:
        return str(value)


class FakeAccountEndpoint:
    def __init__(self, responses: Sequence[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls = 0

    def list(self, **kwargs: Any) -> FakeResponse:
        _ = kwargs
        self.calls += 1
        return self.responses.pop(0)


def test_order_mapper_builds_oanda_order_kwargs() -> None:
    request = OrderRequest(
        request_id=OrderRequestId.new(),
        instrument=USD_JPY,
        side=OrderSide.SELL,
        units=Decimal("1000"),
        order_type=OrderType.MARKET,
    )

    kwargs = OandaOrderMapper().order_kwargs(request)

    assert kwargs["instrument"] == "USD_JPY"
    assert kwargs["units"] == "-1000"
    assert kwargs["clientExtensions"]["id"] == str(request.request_id)


def test_oanda_broker_can_be_created_from_credentials() -> None:
    broker = OandaBroker.from_credentials(
        account_id="001",
        access_token="token-1",
        environment=OandaEnvironment.PRACTICE,
        application="AutoForexTest",
    )

    assert broker.account_id == "001"
    assert broker.gateway.context.token == "token-1"
    assert broker.gateway.context.hostname == "api-fxpractice.oanda.com"


def test_oanda_broker_places_order_and_maps_result() -> None:
    gateway = FakeGateway()
    broker = OandaBroker(
        account_id="001",
        gateway=cast(OandaGateway, gateway),
    )
    request = OrderRequest(
        request_id=OrderRequestId.new(),
        instrument=USD_JPY,
        side=OrderSide.BUY,
        units=Decimal("1000"),
    )

    result = broker.place_order(request)

    assert gateway.market_orders[0]["units"] == "1000"
    assert result.status == OrderStatus.FILLED
    assert str(result.broker_order_id) == "100"
    assert result.filled_units == Decimal("1000")
    assert result.average_fill_price == Money.of("150.12", "JPY")


def test_oanda_broker_maps_positions_and_closes_long_position() -> None:
    gateway = FakeGateway()
    broker = OandaBroker(
        account_id="001",
        gateway=cast(OandaGateway, gateway),
    )

    position = broker.positions(instrument=USD_JPY)[0]
    close_result = broker.close_position(position=position, units=Decimal("250"))

    assert gateway.account_summary_calls == 1
    assert broker.account_currency.code == "USD"
    assert gateway.account_summary_calls == 1
    assert position.side == PositionSide.LONG
    assert str(position.broker_position_id) == "USD_JPY:long"
    assert position.average_entry_price == Money.of("150.10", "JPY")
    assert position.unrealized_pl == Money.of("12.50", "USD")
    assert gateway.close_position_calls[0] == (
        "USD_JPY",
        {"longUnits": "250", "shortUnits": "NONE"},
    )
    assert close_result.status == OrderStatus.FILLED
    assert close_result.average_fill_price == Money.of("150.11", "JPY")


def test_oanda_data_source_maps_ticks_and_candles() -> None:
    source = OandaDataSource(
        account_id="001",
        gateway=cast(OandaGateway, FakeGateway()),
    )

    ticks = tuple(source.ticks(instrument=USD_JPY))
    candles = tuple(source.candles(instrument=USD_JPY, granularity="M1"))

    assert ticks[0].bid == Money.of("150.10", "JPY")
    assert ticks[0].ask == Money.of("150.12", "JPY")
    assert candles[0].open == Money.of("150.00", "JPY")
    assert candles[0].volume == 120


def test_position_mapper_splits_oanda_long_and_short_sides() -> None:
    mapper = OandaPositionMapper(account_currency="USD")
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

    positions = mapper.positions_from_response(response)

    assert [position.side for position in positions] == [PositionSide.LONG, PositionSide.SHORT]


def test_gateway_retries_retryable_api_errors() -> None:
    account = FakeAccountEndpoint(
        [
            FakeResponse(
                500,
                {
                    "errorCode": "INTERNAL_SERVER_ERROR",
                    "errorMessage": "temporary failure",
                },
                "Server Error",
            ),
            FakeResponse(200, {"accounts": []}),
        ]
    )
    gateway = OandaGateway(
        SimpleNamespace(account=account),
        retry_policy=OandaRetryPolicy(
            attempts=2,
            initial_seconds=0,
            max_seconds=0,
        ),
    )

    response = gateway.list_accounts()

    assert response.status == 200
    assert account.calls == 2


def test_gateway_does_not_retry_non_retryable_api_errors() -> None:
    account = FakeAccountEndpoint(
        [
            FakeResponse(
                401,
                {
                    "errorCode": "UNAUTHORIZED",
                    "errorMessage": "invalid token",
                },
                "Unauthorized",
            ),
        ]
    )
    gateway = OandaGateway(
        SimpleNamespace(account=account),
        retry_policy=OandaRetryPolicy(
            attempts=3,
            initial_seconds=0,
            max_seconds=0,
        ),
    )

    with pytest.raises(OandaAuthenticationError):
        gateway.list_accounts()

    assert account.calls == 1
