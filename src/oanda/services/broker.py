"""Internal services used by the OANDA broker facade."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

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

import oanda.models as om
import oanda.payload as payload
from oanda.errors import ensure_success, error_from_response
from oanda.mappers.instrument import OandaInstrumentMapper

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


class OandaMutationResponsePolicy:
    """Classify OANDA mutation responses accepted by broker services."""

    _EXPECTED_STATUSES = frozenset({200, 201, 400, 404})

    @classmethod
    def raise_for_unexpected(cls, response: object) -> None:
        """Raise for mutation response statuses outside the broker contract."""
        status = int(getattr(response, "status", 0) or 0)
        if status in cls._EXPECTED_STATUSES:
            return
        raise error_from_response(response)


class OandaOrderService:
    """Order operations for one OANDA account."""

    def __init__(
        self,
        *,
        account_id: str,
        gateway: OandaOrderGateway,
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

        OandaMutationResponsePolicy.raise_for_unexpected(response)
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
        kwargs = self.close_position_kwargs(side=side, units=requested_units)
        response = self.gateway.close_position(
            self.account_id,
            OandaInstrumentMapper.to_oanda(position.instrument),
            longUnits=kwargs["longUnits"],
            shortUnits=kwargs["shortUnits"],
        )
        OandaMutationResponsePolicy.raise_for_unexpected(response)
        return self.order_mapper.order_from_position_close_response(
            response,
            position=position,
            side=side,
            requested_units=requested_units,
        )

    def list_orders(self, **filters: object) -> Sequence[Metadata]:
        """Return OANDA orders as raw metadata snapshots."""
        response = ensure_success(
            self.gateway.list_orders(
                self.account_id,
                om.OrdersRequest.model_validate(payload.clean(filters)),
            ),
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
            om.ReplaceOrderRequest(order=self._order_request(order)),
            retry=True,
        )
        OandaMutationResponsePolicy.raise_for_unexpected(response)
        return self.order_mapper.order_from_order_response(response, order)

    def cancel_order(self, order_id: str) -> Metadata:
        """Cancel one OANDA order."""
        response = self.gateway.cancel_order(self.account_id, order_id, retry=True)
        OandaMutationResponsePolicy.raise_for_unexpected(response)
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
            om.SetOrderClientExtensionsRequest.model_validate(
                {"clientExtensions": request["clientExtensions"]}
            ),
            retry=True,
        )
        OandaMutationResponsePolicy.raise_for_unexpected(response)
        return payload.metadata(response.body)

    @staticmethod
    def close_position_kwargs(*, side: PositionSide, units: Decimal) -> dict[str, str]:
        """Build OANDA side-specific close-position units."""
        amount = str(units)
        if side == PositionSide.LONG:
            return {"longUnits": amount, "shortUnits": "NONE"}
        return {"longUnits": "NONE", "shortUnits": amount}

    @staticmethod
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

    def _order_request(self, order: Order) -> om.OrderRequestPayload:
        values = {
            **self.order_mapper.order_kwargs(order),
            "type": self.order_type(order.order_type),
        }
        if order.order_type == OrderType.MARKET:
            return om.MarketOrderRequest.model_validate(values)
        if order.order_type == OrderType.LIMIT:
            return om.LimitOrderRequest.model_validate(values)
        if order.order_type == OrderType.STOP:
            return om.StopOrderRequest.model_validate(values)
        msg = f"unsupported OANDA order type: {order.order_type}"
        raise ValueError(msg)


class OandaPositionService:
    """Position operations for one OANDA account."""

    def __init__(
        self,
        *,
        account_id: str,
        gateway: OandaPositionGateway,
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
        gateway: OandaTradeGateway,
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
            self.gateway.list_trades(
                self.account_id,
                om.TradesRequest.model_validate(payload.clean(filters)),
            ),
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
        request = (
            om.CloseTradeRequest.model_validate({"units": str(units)})
            if units is not None
            else None
        )
        response = self.gateway.close_trade(self.account_id, trade_id, request, retry=True)
        OandaMutationResponsePolicy.raise_for_unexpected(response)
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
            om.SetTradeClientExtensionsRequest.model_validate(
                {"clientExtensions": request["clientExtensions"]}
            ),
            retry=True,
        )
        OandaMutationResponsePolicy.raise_for_unexpected(response)
        return payload.metadata(response.body)

    def set_trade_dependent_orders(self, trade_id: str, **orders: object) -> Metadata:
        """Set OANDA dependent orders for a trade."""
        response = self.gateway.set_trade_dependent_orders(
            self.account_id,
            trade_id,
            om.SetTradeDependentOrdersRequest.model_validate(payload.clean(orders)),
            retry=True,
        )
        OandaMutationResponsePolicy.raise_for_unexpected(response)
        return payload.metadata(response.body)

    def _mapper(self) -> Any:
        return self._trade_mapper_factory(account_currency=self._account_currency())


class OandaTransactionService:
    """Transaction operations for one OANDA account."""

    def __init__(
        self,
        *,
        account_id: str,
        gateway: OandaTransactionGateway,
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
                om.TransactionsRequest.model_validate(
                    payload.clean(
                        {
                            "from": self._format_time(from_time),
                            "to": self._format_time(to_time),
                            "pageSize": page_size,
                            "type": tuple(types) if types is not None else None,
                        }
                    )
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
                om.TransactionRangeRequest.model_validate(
                    payload.clean(
                        {
                            "from": from_id,
                            "to": to_id,
                            "type": tuple(types) if types is not None else None,
                        }
                    )
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
                om.TransactionsSinceRequest.model_validate(
                    payload.clean(
                        {
                            "id": transaction_id,
                            "type": tuple(types) if types is not None else None,
                        }
                    )
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
