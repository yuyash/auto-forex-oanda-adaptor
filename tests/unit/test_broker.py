from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from core import (
    Currency,
    CurrencyPair,
    Money,
    Order,
    OrderSide,
    OrderType,
    Position,
    PositionSide,
    PositionSideState,
)

import oanda.broker as broker_module
from oanda.broker import OandaBroker
from tests.support import FakeResponse

USD_JPY = CurrencyPair.of("USD_JPY")


class TestBroker:
    def test_broker_place_order_uses_order_mapper_and_market_gateway(self) -> None:
        gateway = Mock()
        order_mapper = Mock()
        order = Order(instrument=USD_JPY, side=OrderSide.BUY, units=Decimal("1000"))
        result = order.evolve(broker_order_id="100")
        response = FakeResponse(201, {"orderFillTransaction": SimpleNamespace(id="100")})
        order_mapper.order_kwargs.return_value = {"units": "1000", "instrument": "USD_JPY"}
        order_mapper.order_from_order_response.return_value = result
        gateway.create_market_order.return_value = response
        broker = OandaBroker(account_id="001", gateway=gateway, order_mapper=order_mapper)

        assert broker.place_order(order) == result

        gateway.create_market_order.assert_called_once_with(
            "001",
            retry=True,
            units="1000",
            instrument="USD_JPY",
        )
        order_mapper.order_from_order_response.assert_called_once_with(response, order)

    def test_broker_account_currency_is_cached(self) -> None:
        gateway = Mock()
        account_mapper = Mock()
        account_mapper.account_currency_from_response.return_value = Currency.of("USD")
        gateway.get_account_summary.return_value = FakeResponse(
            200, {"account": {"currency": "USD"}}
        )
        broker = OandaBroker(account_id="001", gateway=gateway, account_mapper=account_mapper)

        assert broker.account_currency == Currency.of("USD")
        assert broker.account_currency == Currency.of("USD")
        gateway.get_account_summary.assert_called_once_with("001")

    def test_broker_close_position_builds_oanda_side_request(self) -> None:
        gateway = Mock()
        order_mapper = Mock()
        position = Position(
            instrument=USD_JPY,
            long=PositionSideState(
                side=PositionSide.LONG,
                units=Decimal("1000"),
                average_entry_price=Money.of("150.10", "JPY"),
            ),
        )
        response = FakeResponse(200, {"longOrderFillTransaction": SimpleNamespace(id="10")})
        gateway.close_position.return_value = response
        close_order = Order(
            instrument=USD_JPY,
            side=OrderSide.SELL,
            units=Decimal("250"),
        )
        order_mapper.order_from_position_close_response.return_value = close_order
        broker = OandaBroker(account_id="001", gateway=gateway, order_mapper=order_mapper)

        assert (
            broker.close_position(position=position, side=PositionSide.LONG, units=Decimal("250"))
            == close_order
        )
        gateway.close_position.assert_called_once_with(
            "001",
            "USD_JPY",
            longUnits="250",
            shortUnits="NONE",
        )

    def test_broker_positions_uses_position_mapper(self, monkeypatch: pytest.MonkeyPatch) -> None:
        gateway = Mock()
        account_mapper = Mock()
        mapper = Mock()
        position = Position(
            instrument=USD_JPY,
            long=PositionSideState(
                side=PositionSide.LONG,
                units=Decimal("1000"),
                average_entry_price=Money.of("150.10", "JPY"),
            ),
        )
        account_mapper.account_currency_from_response.return_value = Currency.of("USD")
        gateway.get_account_summary.return_value = FakeResponse(
            200, {"account": {"currency": "USD"}}
        )
        gateway.list_open_positions.return_value = FakeResponse(200, {"positions": []})
        mapper.positions_from_response.return_value = (position,)
        monkeypatch.setattr(broker_module, "OandaPositionMapper", Mock(return_value=mapper))
        broker = OandaBroker(account_id="001", gateway=gateway, account_mapper=account_mapper)

        assert broker.positions(instrument=USD_JPY) == (position,)
        mapper.positions_from_response.assert_called_once_with(
            gateway.list_open_positions.return_value
        )

    def test_broker_trade_and_transaction_methods_use_gateway_and_mapper(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        gateway = Mock()
        account_mapper = Mock()
        trade_mapper = Mock()
        transaction_mapper = Mock()
        account_mapper.account_currency_from_response.return_value = Currency.of("USD")
        gateway.get_account_summary.return_value = FakeResponse(
            200, {"account": {"currency": "USD"}}
        )
        gateway.list_open_trades.return_value = FakeResponse(200, {"trades": []})
        gateway.get_transactions_since.return_value = FakeResponse(200, {"transactions": []})
        trade_mapper.trades_from_response.return_value = ("trade",)
        transaction_mapper.transactions_from_response.return_value = ("transaction",)
        monkeypatch.setattr(broker_module, "OandaTradeMapper", Mock(return_value=trade_mapper))
        monkeypatch.setattr(
            broker_module,
            "OandaTransactionMapper",
            Mock(return_value=transaction_mapper),
        )
        broker = OandaBroker(account_id="001", gateway=gateway, account_mapper=account_mapper)

        assert broker.list_open_trades() == ("trade",)
        assert broker.get_transactions_since("10", types=("ORDER_FILL",)) == ("transaction",)

        gateway.list_open_trades.assert_called_once_with("001")
        gateway.get_transactions_since.assert_called_once_with(
            "001",
            {"id": "10", "type": "ORDER_FILL"},
        )

    def test_broker_order_mutation_results_return_metadata(self) -> None:
        gateway = Mock()
        response = FakeResponse(200, {"lastTransactionID": "10"})
        gateway.cancel_order.return_value = response
        gateway.set_order_client_extensions.return_value = response
        broker = OandaBroker(account_id="001", gateway=gateway)

        assert broker.cancel_order("100")["lastTransactionID"] == "10"
        assert (
            broker.set_order_client_extensions(
                "100", client_id="client", tag="tag", comment="comment"
            )["lastTransactionID"]
            == "10"
        )
        gateway.cancel_order.assert_called_once_with("001", "100", retry=True)
        gateway.set_order_client_extensions.assert_called_once_with(
            "001",
            "100",
            {"clientExtensions": {"id": "client", "tag": "tag", "comment": "comment"}},
            retry=True,
        )

    def test_order_type_helper_maps_core_order_types(self) -> None:
        assert OandaBroker._order_type(OrderType.MARKET) == "MARKET"
        assert OandaBroker._order_type(OrderType.LIMIT) == "LIMIT"
        assert OandaBroker._order_type(OrderType.STOP) == "STOP"
