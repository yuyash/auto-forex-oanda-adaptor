"""Conversions from OANDA snapshots to broker-neutral Core models."""

from __future__ import annotations

from core import Account, AccountSummary, Order, Position, Trade, Transaction

from oanda.snapshots import (
    OandaAccount,
    OandaAccountSummary,
    OandaOrder,
    OandaPosition,
    OandaTrade,
    OandaTransaction,
)


def account_to_core(snapshot: OandaAccount) -> Account:
    """Return the broker-neutral Core account."""
    return snapshot.account


def account_summary_to_core(snapshot: OandaAccountSummary) -> AccountSummary:
    """Return the broker-neutral Core account summary."""
    return snapshot.summary


def order_to_core(snapshot: OandaOrder) -> Order:
    """Return the broker-neutral Core order."""
    return snapshot.order


def position_to_core(snapshot: OandaPosition) -> Position:
    """Return the broker-neutral Core position."""
    return snapshot.position


def trade_to_core(snapshot: OandaTrade) -> Trade:
    """Return the broker-neutral Core trade."""
    return snapshot.trade


def transaction_to_core(snapshot: OandaTransaction) -> Transaction:
    """Return the broker-neutral Core transaction."""
    return snapshot.transaction
