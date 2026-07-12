"""OANDA order service."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from core import Metadata, Order, OrderType, Position, PositionSide, Units

import oanda.models as om
from oanda.errors import OandaResponsePolicy
from oanda.mappers.instrument import OandaInstrumentMapper
from oanda.payload import OandaPayload as payload
from oanda.services.policies import OandaMutationResponsePolicy
from oanda.services.protocols import OandaOrderGateway


class OandaOrderRequestFactory:
    """Build OANDA order request payloads from Core orders."""

    def __init__(self, order_mapper: Any) -> None:
        self.order_mapper = order_mapper

    def request(self, order: Order) -> om.OrderRequestPayload:
        """Return the OANDA order request payload for a Core order."""
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

    @classmethod
    def order_type(cls, order_type_: OrderType) -> str:
        """Map Core order type to OANDA order type text."""
        if order_type_ == OrderType.MARKET:
            return "MARKET"
        if order_type_ == OrderType.LIMIT:
            return "LIMIT"
        if order_type_ == OrderType.STOP:
            return "STOP"
        msg = f"unsupported OANDA order type: {order_type_}"
        raise ValueError(msg)


class OandaPositionCloseRequestFactory:
    """Build OANDA close-position payload fragments."""

    @classmethod
    def kwargs(cls, *, side: PositionSide, units: Units) -> dict[str, str]:
        """Build OANDA side-specific close-position units."""
        amount = str(units)
        if side == PositionSide.LONG:
            return {"longUnits": amount, "shortUnits": "NONE"}
        return {"longUnits": "NONE", "shortUnits": amount}


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
        self.request_factory = OandaOrderRequestFactory(order_mapper)

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
        units: Units | None = None,
    ) -> Order:
        """Close all or part of an OANDA position."""
        state = position.require_side(side)
        source_units = units if units is not None else state.units
        planned_units = Units.of(source_units.copy_abs())
        kwargs = OandaPositionCloseRequestFactory.kwargs(side=side, units=planned_units)
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
            planned_units=planned_units,
        )

    def list_orders(self, **filters: object) -> Sequence[Metadata]:
        """Return OANDA orders as raw metadata snapshots."""
        response = OandaResponsePolicy.ensure_success(
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
        response = OandaResponsePolicy.ensure_success(
            self.gateway.list_pending_orders(self.account_id), 200
        )
        orders = payload.get(response.body, "orders", ()) or ()
        return tuple(payload.metadata(order) for order in orders)

    def get_order(self, order_id: str) -> Metadata:
        """Return one OANDA order as raw metadata."""
        response = OandaResponsePolicy.ensure_success(
            self.gateway.get_order(self.account_id, order_id), 200
        )
        return self.order_mapper.metadata_from_order_response(response)

    def replace_order(self, order_id: str, order: Order) -> Order:
        """Replace one OANDA order."""
        response = self.gateway.replace_order(
            self.account_id,
            order_id,
            om.ReplaceOrderRequest(order=self.request_factory.request(order)),
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
