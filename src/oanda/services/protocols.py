"""Protocols shared by OANDA broker services."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from core import Currency

AccountCurrencyProvider = Callable[[], Currency]
MapperFactory = Callable[..., Any]


class OandaOrderGateway(Protocol):
    """Gateway methods required by order services."""

    def create_market_order(
        self, account_id: str, *, retry: bool = False, **kwargs: Any
    ) -> Any: ...
    def create_limit_order(self, account_id: str, *, retry: bool = False, **kwargs: Any) -> Any: ...
    def create_stop_order(self, account_id: str, *, retry: bool = False, **kwargs: Any) -> Any: ...
    def close_position(self, account_id: str, instrument: str, **kwargs: Any) -> Any: ...
    def list_orders(self, account_id: str, request: Any = None) -> Any: ...
    def list_pending_orders(self, account_id: str) -> Any: ...
    def get_order(self, account_id: str, order_specifier: str) -> Any: ...
    def replace_order(
        self,
        account_id: str,
        order_specifier: str,
        request: Any = None,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> Any: ...
    def cancel_order(
        self,
        account_id: str,
        order_specifier: str,
        *,
        retry: bool = False,
    ) -> Any: ...
    def set_order_client_extensions(
        self,
        account_id: str,
        order_specifier: str,
        request: Any = None,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> Any: ...


class OandaPositionGateway(Protocol):
    """Gateway methods required by position services."""

    def list_open_positions(self, account_id: str) -> Any: ...
    def list_positions(self, account_id: str) -> Any: ...
    def get_position(self, account_id: str, instrument: str) -> Any: ...


class OandaTradeGateway(Protocol):
    """Gateway methods required by trade services."""

    def list_trades(self, account_id: str, request: Any = None) -> Any: ...
    def list_open_trades(self, account_id: str) -> Any: ...
    def get_trade(self, account_id: str, trade_specifier: str) -> Any: ...
    def close_trade(
        self,
        account_id: str,
        trade_specifier: str,
        request: Any = None,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> Any: ...
    def set_trade_client_extensions(
        self,
        account_id: str,
        trade_specifier: str,
        request: Any = None,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> Any: ...
    def set_trade_dependent_orders(
        self,
        account_id: str,
        trade_specifier: str,
        request: Any = None,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> Any: ...


class OandaTransactionGateway(Protocol):
    """Gateway methods required by transaction services."""

    def datetime_to_str(self, value: Any) -> str: ...
    def list_transactions(self, account_id: str, request: Any = None) -> Any: ...
    def get_transaction(self, account_id: str, transaction_id: str) -> Any: ...
    def get_transaction_range(
        self,
        account_id: str,
        request: Any = None,
        **kwargs: Any,
    ) -> Any: ...
    def get_transactions_since(
        self,
        account_id: str,
        request: Any = None,
        **kwargs: Any,
    ) -> Any: ...
    def stream_transactions(self, account_id: str) -> Any: ...
