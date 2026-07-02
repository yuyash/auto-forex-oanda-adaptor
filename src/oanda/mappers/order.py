"""Order mapping between OANDA payloads and Core domain models."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from core import (
    BrokerOrderId,
    CurrencyPair,
    Metadata,
    Money,
    Order,
    OrderReason,
    OrderReasonCode,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    PositionSide,
)

import oanda.payload as payload
from oanda.domain import OandaOrder
from oanda.mappers.instrument import OandaInstrumentMapper


class OandaOrderMapper:
    """Map Core orders and OANDA responses."""

    def order_kwargs(self, order: Order) -> dict[str, Any]:
        """Convert a Core order into OANDA order kwargs."""
        units = self._signed_units(order)
        base: dict[str, Any] = {
            "instrument": OandaInstrumentMapper.to_oanda(order.instrument),
            "units": str(units),
            "positionFill": "DEFAULT",
            "clientExtensions": {
                "id": str(order.id),
                "tag": "auto-forex",
            },
        }

        if order.order_type == OrderType.MARKET:
            return {**base, "timeInForce": "FOK"}

        if order.price is None:
            msg = f"{order.order_type.value} order requires price"
            raise ValueError(msg)

        priced = {
            **base,
            "price": str(order.price.require_currency(order.instrument.quote).amount),
            "timeInForce": "GTC",
        }
        if order.order_type in {OrderType.LIMIT, OrderType.STOP}:
            return priced

        msg = f"unsupported order type: {order.order_type}"
        raise ValueError(msg)

    def order_from_order_response(self, response: Any, order: Order) -> OandaOrder:
        """Convert a create-order response into a normalized OANDA order."""
        body = payload.body(response)
        fill = payload.first(body, "orderFillTransaction")
        cancel = payload.first(body, "orderCancelTransaction")
        reject = payload.first(body, "orderRejectTransaction", "orderReissueRejectTransaction")
        create = payload.first(body, "orderCreateTransaction")
        error_code = str(payload.get(body, "errorCode", "") or "")

        status = self._status_from_transactions(
            response=response,
            fill=fill,
            cancel=cancel,
            reject=reject,
            create=create,
        )
        filled_units = (
            abs(payload.decimal(payload.get(fill, "units", "0")))
            if fill is not None
            else Decimal("0")
        )
        average_fill_price = self._fill_price(fill, order.instrument)
        broker_order_id = self._broker_order_id(fill, create, cancel, reject)
        reason = OrderReason(
            code=self._reason_code(status=status, error_code=error_code),
            details=self._result_details(response, fill, cancel, reject, create),
        )

        return OandaOrder(
            id=order.id,
            status=status,
            broker_order_id=broker_order_id,
            instrument=order.instrument,
            side=order.side,
            units=order.units,
            order_type=order.order_type,
            price=order.price,
            filled_units=filled_units,
            average_fill_price=average_fill_price,
            reason=reason,
            related_transaction_ids=tuple(payload.get(body, "relatedTransactionIDs", ()) or ()),
            last_transaction_id=payload.get(body, "lastTransactionID"),
            metadata=reason.details,
        )

    def metadata_from_order_response(self, response: Any) -> Metadata:
        """Return raw order response metadata for read-only order endpoints."""
        return payload.metadata(payload.body(response))

    def order_from_position_close_response(
        self,
        response: Any,
        *,
        position: Position,
        side: PositionSide,
        requested_units: Decimal,
    ) -> OandaOrder:
        """Convert a close-position response into a normalized OANDA order."""
        body = payload.body(response)
        fill = payload.first(body, "longOrderFillTransaction", "shortOrderFillTransaction")
        cancel = payload.first(body, "longOrderCancelTransaction", "shortOrderCancelTransaction")
        reject = payload.first(body, "longOrderRejectTransaction", "shortOrderRejectTransaction")
        create = payload.first(body, "longOrderCreateTransaction", "shortOrderCreateTransaction")
        error_code = str(payload.get(body, "errorCode", "") or "")
        status = self._status_from_transactions(
            response=response,
            fill=fill,
            cancel=cancel,
            reject=reject,
            create=create,
        )
        reason = OrderReason(
            code=self._reason_code(status=status, error_code=error_code),
            details=self._result_details(response, fill, cancel, reject, create),
        )
        return OandaOrder(
            status=status,
            broker_order_id=self._broker_order_id(fill, create, cancel, reject),
            instrument=position.instrument,
            side=OrderSide.SELL if side == PositionSide.LONG else OrderSide.BUY,
            units=requested_units,
            filled_units=abs(payload.decimal(payload.get(fill, "units", "0")))
            if fill is not None
            else Decimal("0"),
            average_fill_price=self._fill_price(fill, position.instrument),
            reason=reason,
            related_transaction_ids=tuple(payload.get(body, "relatedTransactionIDs", ()) or ()),
            last_transaction_id=payload.get(body, "lastTransactionID"),
            metadata=reason.details,
        )

    @staticmethod
    def _signed_units(order: Order) -> Decimal:
        units = order.units.copy_abs()
        return units if order.side == OrderSide.BUY else -units

    @staticmethod
    def _status_from_transactions(
        *,
        response: Any,
        fill: Any,
        cancel: Any,
        reject: Any,
        create: Any,
    ) -> OrderStatus:
        if reject is not None or int(getattr(response, "status", 0) or 0) >= 400:
            return OrderStatus.REJECTED
        if fill is not None:
            return OrderStatus.FILLED
        if cancel is not None:
            return OrderStatus.CANCELLED
        if create is not None:
            return OrderStatus.ACCEPTED
        return OrderStatus.REJECTED

    @staticmethod
    def _broker_order_id(*transactions: Any) -> BrokerOrderId | None:
        for transaction in transactions:
            if transaction is None:
                continue
            value = payload.get(transaction, "orderID") or payload.get(transaction, "id")
            if value:
                return BrokerOrderId.of(str(value))
        return None

    @staticmethod
    def _fill_price(fill: Any, instrument: CurrencyPair) -> Money | None:
        price = payload.get(fill, "price")
        if price is None:
            return None
        return Money.of(price, instrument.quote)

    @staticmethod
    def _reason_code(*, status: OrderStatus, error_code: str) -> OrderReasonCode:
        normalized = error_code.upper()
        if "INSUFFICIENT_MARGIN" in normalized:
            return OrderReasonCode.INSUFFICIENT_MARGIN
        if "INSTRUMENT" in normalized:
            return OrderReasonCode.INVALID_INSTRUMENT
        if "PRICE" in normalized:
            return OrderReasonCode.INVALID_PRICE
        if "UNITS" in normalized:
            return OrderReasonCode.INVALID_UNITS
        if "MARKET_HALTED" in normalized or "MARKET_CLOSED" in normalized:
            return OrderReasonCode.MARKET_CLOSED
        if "RATE" in normalized:
            return OrderReasonCode.RATE_LIMITED
        if "TIMEOUT" in normalized:
            return OrderReasonCode.TIMEOUT
        if status == OrderStatus.FILLED:
            return OrderReasonCode.FILLED
        if status == OrderStatus.ACCEPTED:
            return OrderReasonCode.ACCEPTED
        if status == OrderStatus.CANCELLED:
            return OrderReasonCode.CANCELLED
        if status == OrderStatus.REJECTED:
            return OrderReasonCode.BROKER_REJECTED
        return OrderReasonCode.UNKNOWN

    @staticmethod
    def _result_details(
        response: Any,
        fill: Any,
        cancel: Any,
        reject: Any,
        create: Any,
    ) -> Metadata:
        details: dict[str, Any] = {
            "oanda_response_status": getattr(response, "status", None),
            "oanda_response_reason": getattr(response, "reason", None),
        }
        body = payload.body(response)
        for key in ("errorCode", "errorMessage", "lastTransactionID", "relatedTransactionIDs"):
            value = payload.get(body, key)
            if value is not None:
                details[key] = value
        for name, transaction in {
            "fill_transaction_id": fill,
            "cancel_transaction_id": cancel,
            "reject_transaction_id": reject,
            "create_transaction_id": create,
        }.items():
            value = payload.get(transaction, "id")
            if value is not None:
                details[name] = value
        return Metadata.model_validate(details)
