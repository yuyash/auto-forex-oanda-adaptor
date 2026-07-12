"""Order mapping between OANDA payloads and Core domain models."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from core import (
    Metadata,
    Order,
    OrderReason,
    OrderSide,
    OrderType,
    Position,
    PositionSide,
    Trade,
    Units,
)

import oanda.models as om
from oanda.mappers.instrument import OandaInstrumentMapper
from oanda.mappers.order_analysis import OandaOrderResponseAnalyzer
from oanda.payload import OandaPayload as payload
from oanda.snapshots import OandaOrder

type OandaOrderMutationResponse = om.OandaResponse[om.OrderTransactionResponse]


class OandaOrderMapper:
    """Map Core orders and OANDA responses."""

    def order_kwargs(self, order: Order) -> dict[str, Any]:
        """Convert a Core order into OANDA order kwargs."""
        units = OandaOrderResponseAnalyzer.signed_units(order)
        logical_trade_id = str(order.metadata.get("logical_trade_id") or order.id)
        base: dict[str, Any] = {
            "instrument": OandaInstrumentMapper.to_oanda(order.instrument),
            "units": str(units),
            "positionFill": "DEFAULT",
            "clientExtensions": {
                "id": str(order.id),
                "tag": "auto-forex",
            },
            "tradeClientExtensions": {
                "id": logical_trade_id,
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

    def order_from_order_response(
        self,
        response: OandaOrderMutationResponse,
        order: Order,
    ) -> Order:
        """Convert a create-order response into a normalized OANDA order."""
        body = payload.body(response)
        fill = payload.first(body, "orderFillTransaction")
        cancel = payload.first(body, "orderCancelTransaction")
        reject = payload.first(body, "orderRejectTransaction", "orderReissueRejectTransaction")
        create = payload.first(body, "orderCreateTransaction")
        error_code = str(payload.get(body, "errorCode", "") or "")

        status = OandaOrderResponseAnalyzer.status_from_transactions(
            response=response,
            fill=fill,
            cancel=cancel,
            reject=reject,
            create=create,
        )
        filled_units = Units.of(
            abs(payload.decimal(payload.get(fill, "units", "0")))
            if fill is not None
            else Decimal("0")
        )
        average_fill_price = OandaOrderResponseAnalyzer.fill_price(fill, order.instrument)
        broker_order_id = OandaOrderResponseAnalyzer.broker_order_id(fill, create, cancel, reject)
        reason = OrderReason(
            code=OandaOrderResponseAnalyzer.reason_code(status=status, error_code=error_code),
            details=OandaOrderResponseAnalyzer.result_details(
                response, fill, cancel, reject, create
            ),
        )

        mapped_order = order.evolve(
            status=status,
            broker_order_id=broker_order_id,
            filled_units=filled_units,
            average_fill_price=average_fill_price,
            reason=reason,
            metadata=order.metadata.merge(reason.details),
        )
        return OandaOrder(
            order=mapped_order,
            related_transaction_ids=tuple(payload.get(body, "relatedTransactionIDs", ()) or ()),
            last_transaction_id=payload.get(body, "lastTransactionID"),
        ).order

    def metadata_from_order_response(
        self, response: om.OandaResponse[om.OrderResponse]
    ) -> Metadata:
        """Return raw order response metadata for read-only order endpoints."""
        return payload.metadata(payload.body(response))

    def order_from_position_close_response(
        self,
        response: om.OandaResponse[om.PositionCloseResponse],
        *,
        position: Position,
        side: PositionSide,
        planned_units: Units,
    ) -> Order:
        """Convert a close-position response into a normalized OANDA order."""
        body = payload.body(response)
        fill = payload.first(body, "longOrderFillTransaction", "shortOrderFillTransaction")
        cancel = payload.first(body, "longOrderCancelTransaction", "shortOrderCancelTransaction")
        reject = payload.first(body, "longOrderRejectTransaction", "shortOrderRejectTransaction")
        create = payload.first(body, "longOrderCreateTransaction", "shortOrderCreateTransaction")
        error_code = str(payload.get(body, "errorCode", "") or "")
        status = OandaOrderResponseAnalyzer.status_from_transactions(
            response=response,
            fill=fill,
            cancel=cancel,
            reject=reject,
            create=create,
        )
        reason = OrderReason(
            code=OandaOrderResponseAnalyzer.reason_code(status=status, error_code=error_code),
            details=OandaOrderResponseAnalyzer.result_details(
                response, fill, cancel, reject, create
            ),
        )
        mapped_order = Order(
            status=status,
            broker_order_id=OandaOrderResponseAnalyzer.broker_order_id(
                fill, create, cancel, reject
            ),
            instrument=position.instrument,
            side=OrderSide.SELL if side == PositionSide.LONG else OrderSide.BUY,
            units=planned_units,
            filled_units=Units.of(
                abs(payload.decimal(payload.get(fill, "units", "0")))
                if fill is not None
                else Decimal("0")
            ),
            average_fill_price=OandaOrderResponseAnalyzer.fill_price(fill, position.instrument),
            reason=reason,
            metadata=reason.details,
        )
        return OandaOrder(
            order=mapped_order,
            related_transaction_ids=tuple(payload.get(body, "relatedTransactionIDs", ()) or ()),
            last_transaction_id=payload.get(body, "lastTransactionID"),
        ).order

    def order_from_trade_close_response(
        self,
        response: om.OandaResponse[om.TradeTransactionResponse],
        *,
        trade: Trade,
        planned_units: Units,
    ) -> Order:
        """Convert a close-trade response into a normalized Core order."""
        body = payload.body(response)
        fill = payload.first(body, "orderFillTransaction")
        cancel = payload.first(body, "orderCancelTransaction")
        reject = payload.first(body, "orderRejectTransaction")
        create = payload.first(body, "orderCreateTransaction")
        error_code = str(payload.get(body, "errorCode", "") or "")
        status = OandaOrderResponseAnalyzer.status_from_transactions(
            response=response,
            fill=fill,
            cancel=cancel,
            reject=reject,
            create=create,
        )
        reason = OrderReason(
            code=OandaOrderResponseAnalyzer.reason_code(status=status, error_code=error_code),
            details=OandaOrderResponseAnalyzer.result_details(
                response, fill, cancel, reject, create
            ),
        )
        mapped_order = Order(
            status=status,
            broker_order_id=OandaOrderResponseAnalyzer.broker_order_id(
                fill, create, cancel, reject
            ),
            instrument=trade.instrument,
            side=OrderSide.SELL if trade.side == PositionSide.LONG else OrderSide.BUY,
            units=planned_units,
            filled_units=Units.of(
                abs(payload.decimal(payload.get(fill, "units", "0")))
                if fill is not None
                else Decimal("0")
            ),
            average_fill_price=OandaOrderResponseAnalyzer.fill_price(fill, trade.instrument),
            reason=reason,
            metadata=trade.metadata.merge(reason.details),
        )
        return OandaOrder(
            order=mapped_order,
            related_transaction_ids=tuple(payload.get(body, "relatedTransactionIDs", ()) or ()),
            last_transaction_id=payload.get(body, "lastTransactionID"),
        ).order
