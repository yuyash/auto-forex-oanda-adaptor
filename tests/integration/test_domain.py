from __future__ import annotations

from core import Account, Order, Position, Trade, Transaction

from oanda.domain import (
    OandaAccount,
    OandaOrder,
    OandaPosition,
    OandaTrade,
    OandaTransaction,
)


class TestDomain:
    def test_domain_models_remain_core_model_subclasses(self) -> None:
        assert issubclass(OandaAccount, Account)
        assert issubclass(OandaOrder, Order)
        assert issubclass(OandaPosition, Position)
        assert issubclass(OandaTrade, Trade)
        assert issubclass(OandaTransaction, Transaction)
