"""Core Broker implementation backed by OANDA v20."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any

from core import (
    Broker,
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

from oanda.config import OandaEnvironment, OandaSettings
from oanda.errors import ensure_success, error_from_response
from oanda.gateway import OandaGateway
from oanda.mappers import (
    OandaAccountMapper,
    OandaInstrumentMapper,
    OandaOrderMapper,
    OandaPositionMapper,
    OandaTradeMapper,
    OandaTransactionMapper,
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

    @classmethod
    def from_settings(cls, settings: OandaSettings) -> OandaBroker:
        """Create an OANDA broker from settings."""
        return cls(
            account_id=settings.account_id,
            gateway=OandaGateway.from_settings(settings),
        )

    @classmethod
    def from_credentials(
        cls,
        *,
        account_id: str,
        access_token: str,
        environment: OandaEnvironment = OandaEnvironment.PRACTICE,
        hostname: str | None = None,
        port: int = 443,
        ssl: bool = True,
        application: str = "AutoForexV2",
        stream_chunk_size: int = 512,
        stream_timeout: int = 60,
        poll_timeout: int = 10,
        retry_attempts: int = 3,
        retry_initial_seconds: float = 0.25,
        retry_max_seconds: float = 4.0,
        retry_multiplier: float = 2.0,
    ) -> OandaBroker:
        """Create an OANDA broker directly from account ID and token."""
        return cls(
            account_id=account_id,
            gateway=OandaGateway.from_credentials(
                access_token=access_token,
                environment=environment,
                hostname=hostname,
                port=port,
                ssl=ssl,
                application=application,
                stream_chunk_size=stream_chunk_size,
                stream_timeout=stream_timeout,
                poll_timeout=poll_timeout,
                retry_attempts=retry_attempts,
                retry_initial_seconds=retry_initial_seconds,
                retry_max_seconds=retry_max_seconds,
                retry_multiplier=retry_multiplier,
            ),
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

        self._raise_unexpected_order_response(response)
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
        kwargs = self._close_position_kwargs(side=side, units=requested_units)
        response = self.gateway.close_position(
            self.account_id,
            OandaInstrumentMapper.to_oanda(position.instrument),
            longUnits=kwargs["longUnits"],
            shortUnits=kwargs["shortUnits"],
        )
        self._raise_unexpected_order_response(response)
        return self.order_mapper.order_from_position_close_response(
            response,
            position=position,
            side=side,
            requested_units=requested_units,
        )

    def positions(self, *, instrument: CurrencyPair | None = None) -> Sequence[Position]:
        """Return open OANDA positions."""
        response = ensure_success(self.gateway.list_open_positions(self.account_id), 200)
        positions = OandaPositionMapper(
            account_currency=self.account_currency,
        ).positions_from_response(response)
        if instrument is None:
            return positions
        return tuple(position for position in positions if position.instrument == instrument)

    def list_orders(self, **filters: object) -> Sequence[Metadata]:
        """Return OANDA orders as raw metadata snapshots."""
        response = ensure_success(
            self.gateway.list_orders(self.account_id, self._clean(filters)),
            200,
        )
        orders = self._get(response.body, "orders", ()) or ()
        return tuple(self._metadata(order) for order in orders)

    def list_pending_orders(self) -> Sequence[Metadata]:
        """Return OANDA pending orders as raw metadata snapshots."""
        response = ensure_success(self.gateway.list_pending_orders(self.account_id), 200)
        orders = self._get(response.body, "orders", ()) or ()
        return tuple(self._metadata(order) for order in orders)

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
                    "type": self._order_type(order.order_type),
                }
            },
            retry=True,
        )
        self._raise_unexpected_order_response(response)
        return self.order_mapper.order_from_order_response(response, order)

    def cancel_order(self, order_id: str) -> Metadata:
        """Cancel one OANDA order."""
        response = self.gateway.cancel_order(self.account_id, order_id, retry=True)
        self._raise_unexpected_order_response(response)
        return self._metadata(response.body)

    def set_order_client_extensions(
        self,
        order_id: str,
        *,
        client_id: str | None = None,
        tag: str | None = None,
        comment: str | None = None,
    ) -> Metadata:
        """Set OANDA order client extensions."""
        request = self._client_extensions(client_id=client_id, tag=tag, comment=comment)
        response = self.gateway.set_order_client_extensions(
            self.account_id,
            order_id,
            request,
            retry=True,
        )
        self._raise_unexpected_order_response(response)
        return self._metadata(response.body)

    def list_trades(self, **filters: object) -> Sequence[Trade]:
        """Return OANDA trades."""
        response = ensure_success(
            self.gateway.list_trades(self.account_id, self._clean(filters)),
            200,
        )
        return OandaTradeMapper(account_currency=self.account_currency).trades_from_response(
            response
        )

    def list_open_trades(self) -> Sequence[Trade]:
        """Return OANDA open trades."""
        response = ensure_success(self.gateway.list_open_trades(self.account_id), 200)
        return OandaTradeMapper(account_currency=self.account_currency).trades_from_response(
            response
        )

    def get_trade(self, trade_id: str) -> Trade:
        """Return one OANDA trade."""
        response = ensure_success(self.gateway.get_trade(self.account_id, trade_id), 200)
        return OandaTradeMapper(account_currency=self.account_currency).trade_from_response(
            response
        )

    def close_trade(self, trade_id: str, *, units: Decimal | None = None) -> Metadata:
        """Close all or part of an OANDA trade."""
        request = {"units": str(units)} if units is not None else None
        response = self.gateway.close_trade(self.account_id, trade_id, request, retry=True)
        self._raise_unexpected_order_response(response)
        return self._metadata(response.body)

    def set_trade_client_extensions(
        self,
        trade_id: str,
        *,
        client_id: str | None = None,
        tag: str | None = None,
        comment: str | None = None,
    ) -> Metadata:
        """Set OANDA trade client extensions."""
        request = self._client_extensions(client_id=client_id, tag=tag, comment=comment)
        response = self.gateway.set_trade_client_extensions(
            self.account_id,
            trade_id,
            request,
            retry=True,
        )
        self._raise_unexpected_order_response(response)
        return self._metadata(response.body)

    def set_trade_dependent_orders(self, trade_id: str, **orders: object) -> Metadata:
        """Set OANDA dependent orders for a trade."""
        response = self.gateway.set_trade_dependent_orders(
            self.account_id,
            trade_id,
            self._clean(orders),
            retry=True,
        )
        self._raise_unexpected_order_response(response)
        return self._metadata(response.body)

    def list_positions(self) -> Sequence[Position]:
        """Return all OANDA positions."""
        response = ensure_success(self.gateway.list_positions(self.account_id), 200)
        return OandaPositionMapper(account_currency=self.account_currency).positions_from_response(
            response
        )

    def list_open_positions(self) -> Sequence[Position]:
        """Return open OANDA positions."""
        return self.positions()

    def get_position(self, instrument: CurrencyPair) -> Position:
        """Return one OANDA position."""
        response = ensure_success(
            self.gateway.get_position(self.account_id, OandaInstrumentMapper.to_oanda(instrument)),
            200,
        )
        position = OandaPositionMapper(account_currency=self.account_currency).position_from_oanda(
            self._get(response.body, "position")
        )
        if position is None:
            msg = f"position not found: {instrument}"
            raise LookupError(msg)
        return position

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
                self._clean(
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
        return self._metadata(response.body)

    def get_transaction(self, transaction_id: str) -> Transaction:
        """Return one OANDA transaction."""
        response = ensure_success(
            self.gateway.get_transaction(self.account_id, transaction_id), 200
        )
        return OandaTransactionMapper(
            account_currency=self.account_currency
        ).transaction_from_response(response)

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
                self._clean(
                    {
                        "from": from_id,
                        "to": to_id,
                        "type": ",".join(types) if types is not None else None,
                    }
                ),
            ),
            200,
        )
        return OandaTransactionMapper(
            account_currency=self.account_currency
        ).transactions_from_response(response)

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
                self._clean(
                    {
                        "id": transaction_id,
                        "type": ",".join(types) if types is not None else None,
                    }
                ),
            ),
            200,
        )
        return OandaTransactionMapper(
            account_currency=self.account_currency
        ).transactions_from_response(response)

    def stream_transactions(self) -> Iterable[Transaction]:
        """Yield OANDA transaction stream updates."""
        response = self.gateway.stream_transactions(self.account_id)
        mapper = OandaTransactionMapper(account_currency=self.account_currency)
        for part_type, value in response.parts():
            if part_type.endswith("Heartbeat"):
                continue
            yield mapper.transaction_from_oanda(value)

    @staticmethod
    def _close_position_kwargs(*, side: PositionSide, units: Decimal) -> dict[str, str]:
        amount = str(units)
        if side == PositionSide.LONG:
            return {"longUnits": amount, "shortUnits": "NONE"}
        return {"longUnits": "NONE", "shortUnits": amount}

    @staticmethod
    def _raise_unexpected_order_response(response: object) -> None:
        status = int(getattr(response, "status", 0) or 0)
        if status in {200, 201, 400, 404}:
            return
        raise error_from_response(response)

    def _format_time(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return self.gateway.datetime_to_str(value)

    @staticmethod
    def _metadata(value: Any) -> Metadata:
        if hasattr(value, "model_dump"):
            return Metadata.model_validate(
                value.model_dump(mode="json", by_alias=True, exclude_none=True)
            )
        if isinstance(value, Mapping):
            return Metadata.model_validate(dict(value))
        return Metadata.model_validate(
            {
                key: item
                for key in dir(value)
                if not key.startswith("_") and not callable(item := getattr(value, key))
            }
        )

    @staticmethod
    def _get(value: Any, key: str, default: Any = None) -> Any:
        if value is None:
            return default
        if isinstance(value, Mapping):
            return value.get(key, default)
        return getattr(value, key, default)

    @staticmethod
    def _clean(values: Mapping[str, object]) -> dict[str, object]:
        return {key: value for key, value in values.items() if value is not None}

    @classmethod
    def _client_extensions(
        cls,
        *,
        client_id: str | None,
        tag: str | None,
        comment: str | None,
    ) -> dict[str, dict[str, str]]:
        extensions = cls._clean({"id": client_id, "tag": tag, "comment": comment})
        return {"clientExtensions": {key: str(value) for key, value in extensions.items()}}

    @staticmethod
    def _order_type(order_type: OrderType) -> str:
        if order_type == OrderType.MARKET:
            return "MARKET"
        if order_type == OrderType.LIMIT:
            return "LIMIT"
        if order_type == OrderType.STOP:
            return "STOP"
        msg = f"unsupported OANDA order type: {order_type}"
        raise ValueError(msg)
