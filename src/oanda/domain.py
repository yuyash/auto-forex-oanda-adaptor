"""OANDA-normalized domain models built on Core models."""

from __future__ import annotations

from decimal import Decimal

from core import (
    Account,
    AccountProvider,
    AccountSummary,
    Metadata,
    Order,
    Position,
    Trade,
    Transaction,
)
from pydantic import Field, model_validator


class OandaAccount(Account):
    """Core Account with OANDA-specific identifiers and tags."""

    provider: AccountProvider = AccountProvider.OANDA
    mt4_account_id: int | None = None
    tags: tuple[str, ...] = ()
    last_transaction_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="before")
    @classmethod
    def _force_provider(cls, data: object) -> object:
        if isinstance(data, dict):
            normalized = dict(data)
            normalized["provider"] = AccountProvider.OANDA
            return normalized
        return data


class OandaAccountSummary(AccountSummary):
    """Core AccountSummary with OANDA account-state details."""

    financing_mode: str | None = None
    hedging_enabled: bool | None = None
    position_aggregation_mode: str | None = None
    guaranteed_stop_loss_order_mode: str | None = None
    withdrawal_limit: Decimal | None = None
    last_transaction_id: str | None = Field(default=None, min_length=1)
    metadata: Metadata = Field(default_factory=Metadata)


class OandaOrder(Order):
    """Core Order with OANDA order and transaction metadata."""

    client_order_id: str | None = None
    client_order_tag: str | None = None
    time_in_force: str | None = None
    position_fill: str | None = None
    trigger_condition: str | None = None
    related_transaction_ids: tuple[str, ...] = ()
    last_transaction_id: str | None = Field(default=None, min_length=1)
    metadata: Metadata = Field(default_factory=Metadata)


class OandaPosition(Position):
    """Core two-sided Position with OANDA position accounting fields."""

    pl: Decimal | None = None
    resettable_pl: Decimal | None = None
    financing: Decimal | None = None
    margin_used: Decimal | None = None
    long_trade_ids: tuple[str, ...] = ()
    short_trade_ids: tuple[str, ...] = ()
    metadata: Metadata = Field(default_factory=Metadata)


class OandaTrade(Trade):
    """Core Trade with OANDA trade metadata."""

    client_trade_id: str | None = None
    initial_units: Decimal | None = None
    initial_margin_required: Decimal | None = None
    realized_pl_value: Decimal | None = None
    financing: Decimal | None = None
    dividend_adjustment: Decimal | None = None
    close_transaction_ids: tuple[str, ...] = ()
    metadata: Metadata = Field(default_factory=Metadata)


class OandaTransaction(Transaction):
    """Core Transaction with OANDA transaction metadata."""

    user_id: int | None = None
    batch_id: str | None = None
    request_id: str | None = None
    reason: str | None = None
    reject_reason: str | None = None
    related_transaction_ids: tuple[str, ...] = ()
    metadata: Metadata = Field(default_factory=Metadata)
