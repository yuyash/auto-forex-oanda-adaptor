"""Core Broker implementation backed by OANDA v20."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime
from decimal import Decimal

from core import (
    Broker,
    Currency,
    CurrencyPair,
    Metadata,
    Order,
    Position,
    PositionSide,
    Trade,
    Transaction,
)

from oanda.config import OandaSettings
from oanda.errors import ensure_success
from oanda.gateway import OandaGateway
from oanda.mappers import (
    OandaAccountMapper,
    OandaOrderMapper,
    OandaPositionMapper,
    OandaTradeMapper,
    OandaTransactionMapper,
)
from oanda.services.broker import (
    OandaOrderService,
    OandaPositionService,
    OandaTradeService,
    OandaTransactionService,
)


class OandaBroker(Broker):
    """Broker port implementation that executes orders through OANDA v20."""

    def __init__(
        self,
        *,
        account_id: str,
        gateway: OandaGateway,
        account_mapper: OandaAccountMapper | None = None,
        order_mapper: OandaOrderMapper | None = None,
    ) -> None:
        self.account_id = account_id
        self.gateway = gateway
        self.account_mapper = account_mapper or OandaAccountMapper()
        self.order_mapper = order_mapper or OandaOrderMapper()
        self._account_currency: Currency | None = None
        self._orders = OandaOrderService(
            account_id=account_id,
            gateway=gateway,
            order_mapper=self.order_mapper,
        )
        self._positions = OandaPositionService(
            account_id=account_id,
            gateway=gateway,
            account_currency=lambda: self.account_currency,
            position_mapper_factory=OandaPositionMapper,
        )
        self._trades = OandaTradeService(
            account_id=account_id,
            gateway=gateway,
            account_currency=lambda: self.account_currency,
            trade_mapper_factory=OandaTradeMapper,
        )
        self._transactions = OandaTransactionService(
            account_id=account_id,
            gateway=gateway,
            account_currency=lambda: self.account_currency,
            transaction_mapper_factory=OandaTransactionMapper,
        )

    @classmethod
    def from_settings(cls, settings: OandaSettings) -> OandaBroker:
        """Create an OANDA broker from settings."""
        return cls(
            account_id=settings.account_id,
            gateway=OandaGateway.from_settings(settings),
        )

    @property
    def account_currency(self) -> Currency:
        """Return the OANDA account home currency, loaded from account summary."""
        if self._account_currency is None:
            response = ensure_success(self.gateway.get_account_summary(self.account_id), 200)
            self._account_currency = self.account_mapper.account_currency_from_response(response)
        return self._account_currency

    def place_order(self, order: Order) -> Order:
        """Place an order through OANDA."""
        return self._orders.place_order(order)

    def close_position(
        self,
        *,
        position: Position,
        side: PositionSide,
        units: Decimal | None = None,
    ) -> Order:
        """Close all or part of an OANDA position."""
        return self._orders.close_position(position=position, side=side, units=units)

    def positions(self, *, instrument: CurrencyPair | None = None) -> Sequence[Position]:
        """Return open OANDA positions."""
        return self._positions.positions(instrument=instrument)

    def list_orders(self, **filters: object) -> Sequence[Metadata]:
        """Return OANDA orders as raw metadata snapshots."""
        return self._orders.list_orders(**filters)

    def list_pending_orders(self) -> Sequence[Metadata]:
        """Return OANDA pending orders as raw metadata snapshots."""
        return self._orders.list_pending_orders()

    def get_order(self, order_id: str) -> Metadata:
        """Return one OANDA order as raw metadata."""
        return self._orders.get_order(order_id)

    def replace_order(self, order_id: str, order: Order) -> Order:
        """Replace one OANDA order."""
        return self._orders.replace_order(order_id, order)

    def cancel_order(self, order_id: str) -> Metadata:
        """Cancel one OANDA order."""
        return self._orders.cancel_order(order_id)

    def set_order_client_extensions(
        self,
        order_id: str,
        *,
        client_id: str | None = None,
        tag: str | None = None,
        comment: str | None = None,
    ) -> Metadata:
        """Set OANDA order client extensions."""
        return self._orders.set_order_client_extensions(
            order_id,
            client_id=client_id,
            tag=tag,
            comment=comment,
        )

    def list_trades(self, **filters: object) -> Sequence[Trade]:
        """Return OANDA trades."""
        return self._trades.list_trades(**filters)

    def list_open_trades(self) -> Sequence[Trade]:
        """Return OANDA open trades."""
        return self._trades.list_open_trades()

    def get_trade(self, trade_id: str) -> Trade:
        """Return one OANDA trade."""
        return self._trades.get_trade(trade_id)

    def close_trade(self, trade_id: str, *, units: Decimal | None = None) -> Metadata:
        """Close all or part of an OANDA trade."""
        return self._trades.close_trade(trade_id, units=units)

    def set_trade_client_extensions(
        self,
        trade_id: str,
        *,
        client_id: str | None = None,
        tag: str | None = None,
        comment: str | None = None,
    ) -> Metadata:
        """Set OANDA trade client extensions."""
        return self._trades.set_trade_client_extensions(
            trade_id,
            client_id=client_id,
            tag=tag,
            comment=comment,
        )

    def set_trade_dependent_orders(self, trade_id: str, **orders: object) -> Metadata:
        """Set OANDA dependent orders for a trade."""
        return self._trades.set_trade_dependent_orders(trade_id, **orders)

    def list_positions(self) -> Sequence[Position]:
        """Return all OANDA positions."""
        return self._positions.list_positions()

    def list_open_positions(self) -> Sequence[Position]:
        """Return open OANDA positions."""
        return self._positions.list_open_positions()

    def get_position(self, instrument: CurrencyPair) -> Position:
        """Return one OANDA position."""
        return self._positions.get_position(instrument)

    def list_transactions(
        self,
        *,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        page_size: int | None = None,
        types: Iterable[str] | None = None,
    ) -> Metadata:
        """Return OANDA transaction page metadata."""
        return self._transactions.list_transactions(
            from_time=from_time,
            to_time=to_time,
            page_size=page_size,
            types=types,
        )

    def get_transaction(self, transaction_id: str) -> Transaction:
        """Return one OANDA transaction."""
        return self._transactions.get_transaction(transaction_id)

    def get_transaction_range(
        self,
        *,
        from_id: str | None = None,
        to_id: str | None = None,
        types: Iterable[str] | None = None,
    ) -> Sequence[Transaction]:
        """Return OANDA transactions by ID range."""
        return self._transactions.get_transaction_range(
            from_id=from_id,
            to_id=to_id,
            types=types,
        )

    def get_transactions_since(
        self,
        transaction_id: str,
        *,
        types: Iterable[str] | None = None,
    ) -> Sequence[Transaction]:
        """Return OANDA transactions since one transaction ID."""
        return self._transactions.get_transactions_since(transaction_id, types=types)

    def stream_transactions(self) -> Iterable[Transaction]:
        """Yield OANDA transaction stream updates."""
        return self._transactions.stream_transactions()

    def _format_time(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return self.gateway.datetime_to_str(value)
