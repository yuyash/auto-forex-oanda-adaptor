"""Backward-compatible OANDA domain exports."""

from __future__ import annotations

from oanda.converters import (
    account_summary_to_core,
    account_to_core,
    order_to_core,
    position_to_core,
    trade_to_core,
    transaction_to_core,
)
from oanda.snapshots import (
    OandaAccount,
    OandaAccountSummary,
    OandaOrder,
    OandaPosition,
    OandaTrade,
    OandaTransaction,
)

__all__ = [
    "OandaAccount",
    "OandaAccountSummary",
    "OandaOrder",
    "OandaPosition",
    "OandaTrade",
    "OandaTransaction",
    "account_summary_to_core",
    "account_to_core",
    "order_to_core",
    "position_to_core",
    "trade_to_core",
    "transaction_to_core",
]
