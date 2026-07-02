from __future__ import annotations

from decimal import Decimal

from core import Money, OrderSide, PositionSide

from oanda import OANDA_PROVIDER
from oanda.domain import (
    OandaAccount,
    OandaAccountSummary,
    OandaOrder,
    OandaPosition,
    OandaTrade,
    OandaTransaction,
)


class TestDomain:
    def test_oanda_account_forces_oanda_provider(self) -> None:
        account = OandaAccount.model_validate(
            {
                "id": "001",
                "provider": None,
                "alias": "primary",
                "mt4_account_id": 123,
                "tags": ("demo",),
            }
        )

        assert account.provider == OANDA_PROVIDER
        assert account.mt4_account_id == 123
        assert account.tags == ("demo",)

    def test_oanda_account_summary_accepts_oanda_specific_fields(self) -> None:
        summary = OandaAccountSummary.model_validate(
            {
                "account_id": "001",
                "currency": "USD",
                "balance": "1000.00",
                "financing_mode": "NO_FINANCING",
                "hedging_enabled": True,
                "withdrawal_limit": "900.00",
            }
        )

        assert summary.balance == Money.of("1000.00", "USD")
        assert summary.financing_mode == "NO_FINANCING"
        assert summary.withdrawal_limit == Decimal("900.00")

    def test_oanda_order_position_trade_and_transaction_extend_core_models(self) -> None:
        order = OandaOrder.model_validate(
            {
                "instrument": "USD_JPY",
                "side": "buy",
                "units": "1000",
                "client_order_id": "client-1",
                "related_transaction_ids": ("10",),
            }
        )
        position = OandaPosition.model_validate(
            {
                "instrument": "USD_JPY",
                "long": {
                    "side": "long",
                    "units": "1000",
                    "average_entry_price": "150.10",
                },
                "pl": "1.25",
            }
        )
        trade = OandaTrade.model_validate(
            {
                "id": "200",
                "instrument": "USD_JPY",
                "side": "long",
                "units": "1000",
                "initial_units": "1000",
                "financing": "0.10",
            }
        )
        transaction = OandaTransaction.model_validate(
            {
                "id": "300",
                "type": "ORDER_FILL",
                "reason": "MARKET_ORDER",
                "related_transaction_ids": ("299", "300"),
            }
        )

        assert order.side == OrderSide.BUY
        assert order.client_order_id == "client-1"
        assert position.long is not None
        assert position.long.side == PositionSide.LONG
        assert position.pl == Decimal("1.25")
        assert trade.initial_units == Decimal("1000")
        assert trade.financing == Decimal("0.10")
        assert transaction.reason == "MARKET_ORDER"
