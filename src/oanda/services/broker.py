"""Internal services used by the OANDA broker facade."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any

from core import (
    Currency,
    CurrencyPair,
    Metadata,
    Order,
    OrderType,
    Position,
    PositionSide,
    Trade,
    Transaction,
)

import oanda.payload as payload
from oanda.errors import ensure_success, error_from_response
from oanda.gateway import OandaGateway
from oanda.mappers.instrument import OandaInstrumentMapper

AccountCurrencyProvider = Callable[[], Currency]
MapperFactory = Callable[..., Any]


def close_position_kwargs(*, side: PositionSide, units: Decimal) -> dict[str, str]:
    """Build OANDA side-specific close-position units."""
    amount = str(units)
    if side == PositionSide.LONG:
        return {"longUnits": amount, "shortUnits": "NONE"}
    return {"longUnits": "NONE", "shortUnits": amount}


def raise_unexpected_order_response(response: object) -> None:
    """Raise for unexpected mutation response statuses."""
    status = int(getattr(response, "status", 0) or 0)
    if status in {200, 201, 400, 404}:
        return
    raise error_from_response(response)


def order_type(order_type_: OrderType) -> str:
    """Map Core order type to OANDA order type text."""
    if order_type_ == OrderType.MARKET:
        return "MARKET"
    if order_type_ == OrderType.LIMIT:
        return "LIMIT"
    if order_type_ == OrderType.STOP:
        return "STOP"
    msg = f"unsupported OANDA order type: {order_type_}"
    raise ValueError(msg)


class OandaOrderService:
    """Order operations for one OANDA account."""

    def __init__(
        self,
        *,
        account_id: str,
        gateway: OandaGateway,
        order_mapper: Any,
    ) -> None:
        self.account_id = account_id
        self.gateway = gateway
        self.order_mapper = order_mapper

    def place_order(self, order: Order) -> Order:
        """Place an order through OANDA."""
        kwargs = self.order_mapper.order_kwargs(order)
        if order.order_type == OrderType.MARKET:
            response = self.gateway.create_market_order(self.account_id, retry=True, **kwargs)
        elif order.order_type == OrderType.LIMIT:
            response = self.gateway.create_limit_order(self.account_id, retry=True, **kwargs)
        elif order.order_type == OrderType.STOP:
            response = self.gateway.create_stop_order(self.account_id, retry=True, **kwargs)
        else:
            msg = f"unsupported OANDA order type: {order.order_type}"
            raise ValueError(msg)

        raise_unexpected_order_response(response)
        return self.order_mapper.order_from_order_response(response, order)

    def close_position(
        self,
        *,
        position: Position,
        side: PositionSide,
        units: Decimal | None = None,
    ) -> Order:
        """Close all or part of an OANDA position."""
        state = position.require_side(side)
        requested_units = (units or state.units).copy_abs()
        kwargs = close_position_kwargs(side=side, units=requested_units)
        response = self.gateway.close_position(
            self.account_id,
            OandaInstrumentMapper.to_oanda(position.instrument),
            longUnits=kwargs["longUnits"],
            shortUnits=kwargs["shortUnits"],
        )
        raise_unexpected_order_response(response)
        return self.order_mapper.order_from_position_close_response(
            response,
            position=position,
            side=side,
            requested_units=requested_units,
        )

    def list_orders(self, **filters: object) -> Sequence[Metadata]:
        """Return OANDA orders as raw metadata snapshots."""
        response = ensure_success(
            self.gateway.list_orders(self.account_id, payload.clean(filters)),
            200,
        )
        orders = payload.get(response.body, "orders", ()) or ()
        return tuple(payload.metadata(order) for order in orders)

    def list_pending_orders(self) -> Sequence[Metadata]:
        """Return OANDA pending orders as raw metadata snapshots."""
        response = ensure_success(self.gateway.list_pending_orders(self.account_id), 200)
        orders = payload.get(response.body, "orders", ()) or ()
        return tuple(payload.metadata(order) for order in orders)

    def get_order(self, order_id: str) -> Metadata:
        """Return one OANDA order as raw metadata."""
        response = ensure_success(self.gateway.get_order(self.account_id, order_id), 200)
        return self.order_mapper.metadata_from_order_response(response)

    def replace_order(self, order_id: str, order: Order) -> Order:
        """Replace one OANDA order."""
        response = self.gateway.replace_order(
            self.account_id,
            order_id,
            {
                "order": {
                    **self.order_mapper.order_kwargs(order),
                    "type": order_type(order.order_type),
                }
            },
            retry=True,
        )
        raise_unexpected_order_response(response)
        return self.order_mapper.order_from_order_response(response, order)

    def cancel_order(self, order_id: str) -> Metadata:
        """Cancel one OANDA order."""
        response = self.gateway.cancel_order(self.account_id, order_id, retry=True)
        raise_unexpected_order_response(response)
        return payload.metadata(response.body)

    def set_order_client_extensions(
        self,
        order_id: str,
        *,
        client_id: str | None = None,
        tag: str | None = None,
        comment: str | None = None,
    ) -> Metadata:
        """Set OANDA order client extensions."""
        request = payload.client_extensions(client_id=client_id, tag=tag, comment=comment)
        response = self.gateway.set_order_client_extensions(
            self.account_id,
            order_id,
            request,
            retry=True,
        )
        raise_unexpected_order_response(response)
        return payload.metadata(response.body)


class OandaPositionService:
    """Position operations for one OANDA account."""

    def __init__(
        self,
        *,
        account_id: str,
        gateway: OandaGateway,
        account_currency: AccountCurrencyProvider,
        position_mapper_factory: MapperFactory,
    ) -> None:
        self.account_id = account_id
        self.gateway = gateway
        self._account_currency = account_currency
        self._position_mapper_factory = position_mapper_factory

    def positions(self, *, instrument: CurrencyPair | None = None) -> Sequence[Position]:
        """Return open OANDA positions."""
        response = ensure_success(self.gateway.list_open_positions(self.account_id), 200)
        positions = self._mapper().positions_from_response(response)
        if instrument is None:
            return positions
        return tuple(position for position in positions if position.instrument == instrument)

    def list_positions(self) -> Sequence[Position]:
        """Return all OANDA positions."""
        response = ensure_success(self.gateway.list_positions(self.account_id), 200)
        return self._mapper().positions_from_response(response)

    def list_open_positions(self) -> Sequence[Position]:
        """Return open OANDA positions."""
        return self.positions()

    def get_position(self, instrument: CurrencyPair) -> Position:
        """Return one OANDA position."""
        response = ensure_success(
            self.gateway.get_position(self.account_id, OandaInstrumentMapper.to_oanda(instrument)),
            200,
        )
        position = self._mapper().position_from_oanda(payload.get(response.body, "position"))
        if position is None:
            msg = f"position not found: {instrument}"
            raise LookupError(msg)
        return position

    def _mapper(self) -> Any:
        return self._position_mapper_factory(account_currency=self._account_currency())


class OandaTradeService:
    """Trade operations for one OANDA account."""

    def __init__(
        self,
        *,
        account_id: str,
        gateway: OandaGateway,
        account_currency: AccountCurrencyProvider,
        trade_mapper_factory: MapperFactory,
    ) -> None:
        self.account_id = account_id
        self.gateway = gateway
        self._account_currency = account_currency
        self._trade_mapper_factory = trade_mapper_factory

    def list_trades(self, **filters: object) -> Sequence[Trade]:
        """Return OANDA trades."""
        response = ensure_success(
            self.gateway.list_trades(self.account_id, payload.clean(filters)),
            200,
        )
        return self._mapper().trades_from_response(response)

    def list_open_trades(self) -> Sequence[Trade]:
        """Return OANDA open trades."""
        response = ensure_success(self.gateway.list_open_trades(self.account_id), 200)
        return self._mapper().trades_from_response(response)

    def get_trade(self, trade_id: str) -> Trade:
        """Return one OANDA trade."""
        response = ensure_success(self.gateway.get_trade(self.account_id, trade_id), 200)
        return self._mapper().trade_from_response(response)

    def close_trade(self, trade_id: str, *, units: Decimal | None = None) -> Metadata:
        """Close all or part of an OANDA trade."""
        request = {"units": str(units)} if units is not None else None
        response = self.gateway.close_trade(self.account_id, trade_id, request, retry=True)
        raise_unexpected_order_response(response)
        return payload.metadata(response.body)

    def set_trade_client_extensions(
        self,
        trade_id: str,
        *,
        client_id: str | None = None,
        tag: str | None = None,
        comment: str | None = None,
    ) -> Metadata:
        """Set OANDA trade client extensions."""
        request = payload.client_extensions(client_id=client_id, tag=tag, comment=comment)
        response = self.gateway.set_trade_client_extensions(
            self.account_id,
            trade_id,
            request,
            retry=True,
        )
        raise_unexpected_order_response(response)
        return payload.metadata(response.body)

    def set_trade_dependent_orders(self, trade_id: str, **orders: object) -> Metadata:
        """Set OANDA dependent orders for a trade."""
        response = self.gateway.set_trade_dependent_orders(
            self.account_id,
            trade_id,
            payload.clean(orders),
            retry=True,
        )
        raise_unexpected_order_response(response)
        return payload.metadata(response.body)

    def _mapper(self) -> Any:
        return self._trade_mapper_factory(account_currency=self._account_currency())


class OandaTransactionService:
    """Transaction operations for one OANDA account."""

    def __init__(
        self,
        *,
        account_id: str,
        gateway: OandaGateway,
        account_currency: AccountCurrencyProvider,
        transaction_mapper_factory: MapperFactory,
    ) -> None:
        self.account_id = account_id
        self.gateway = gateway
        self._account_currency = account_currency
        self._transaction_mapper_factory = transaction_mapper_factory

    def list_transactions(
        self,
        *,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        page_size: int | None = None,
        types: Iterable[str] | None = None,
    ) -> Metadata:
        """Return OANDA transaction page metadata."""
        response = ensure_success(
            self.gateway.list_transactions(
                self.account_id,
                payload.clean(
                    {
                        "from": self._format_time(from_time),
                        "to": self._format_time(to_time),
                        "pageSize": page_size,
                        "type": ",".join(types) if types is not None else None,
                    }
                ),
            ),
            200,
        )
        return payload.metadata(response.body)

    def get_transaction(self, transaction_id: str) -> Transaction:
        """Return one OANDA transaction."""
        response = ensure_success(
            self.gateway.get_transaction(self.account_id, transaction_id), 200
        )
        return self._mapper().transaction_from_response(response)

    def get_transaction_range(
        self,
        *,
        from_id: str | None = None,
        to_id: str | None = None,
        types: Iterable[str] | None = None,
    ) -> Sequence[Transaction]:
        """Return OANDA transactions by ID range."""
        response = ensure_success(
            self.gateway.get_transaction_range(
                self.account_id,
                payload.clean(
                    {
                        "from": from_id,
                        "to": to_id,
                        "type": ",".join(types) if types is not None else None,
                    }
                ),
            ),
            200,
        )
        return self._mapper().transactions_from_response(response)

    def get_transactions_since(
        self,
        transaction_id: str,
        *,
        types: Iterable[str] | None = None,
    ) -> Sequence[Transaction]:
        """Return OANDA transactions since one transaction ID."""
        response = ensure_success(
            self.gateway.get_transactions_since(
                self.account_id,
                payload.clean(
                    {
                        "id": transaction_id,
                        "type": ",".join(types) if types is not None else None,
                    }
                ),
            ),
            200,
        )
        return self._mapper().transactions_from_response(response)

    def stream_transactions(self) -> Iterable[Transaction]:
        """Yield OANDA transaction stream updates."""
        response = self.gateway.stream_transactions(self.account_id)
        mapper = self._mapper()
        for part_type, value in response.parts():
            if part_type.endswith("Heartbeat"):
                continue
            yield mapper.transaction_from_oanda(value)

    def _format_time(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return self.gateway.datetime_to_str(value)

    def _mapper(self) -> Any:
        return self._transaction_mapper_factory(account_currency=self._account_currency())
