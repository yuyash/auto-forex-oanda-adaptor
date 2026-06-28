"""Core Broker implementation backed by OANDA v20."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from core import (
    Broker,
    Currency,
    CurrencyPair,
    OrderRequest,
    OrderResult,
    OrderType,
    Position,
    PositionSide,
)

from oanda.config import OandaEnvironment, OandaSettings
from oanda.errors import ensure_success, error_from_response
from oanda.gateway import OandaGateway
from oanda.mappers import (
    OandaAccountMapper,
    OandaInstrumentMapper,
    OandaOrderMapper,
    OandaPositionMapper,
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

    def place_order(self, request: OrderRequest) -> OrderResult:
        """Place an order through OANDA."""
        kwargs = self.order_mapper.order_kwargs(request)
        if request.order_type == OrderType.MARKET:
            response = self.gateway.create_market_order(self.account_id, retry=True, **kwargs)
        elif request.order_type == OrderType.LIMIT:
            response = self.gateway.create_limit_order(self.account_id, retry=True, **kwargs)
        elif request.order_type == OrderType.STOP:
            response = self.gateway.create_stop_order(self.account_id, retry=True, **kwargs)
        else:
            msg = f"unsupported OANDA order type: {request.order_type}"
            raise ValueError(msg)

        self._raise_unexpected_order_response(response)
        return self.order_mapper.result_from_order_response(response, request)

    def close_position(
        self,
        *,
        position: Position,
        units: Decimal | None = None,
    ) -> OrderResult:
        """Close all or part of an OANDA position."""
        requested_units = (units or position.units).copy_abs()
        kwargs = self._close_position_kwargs(position=position, units=requested_units)
        response = self.gateway.close_position(
            self.account_id,
            OandaInstrumentMapper.to_oanda(position.instrument),
            longUnits=kwargs["longUnits"],
            shortUnits=kwargs["shortUnits"],
        )
        self._raise_unexpected_order_response(response)
        return self.order_mapper.result_from_position_close_response(
            response,
            position=position,
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

    @staticmethod
    def _close_position_kwargs(*, position: Position, units: Decimal) -> dict[str, str]:
        amount = str(units)
        if position.side == PositionSide.LONG:
            return {"longUnits": amount, "shortUnits": "NONE"}
        return {"longUnits": "NONE", "shortUnits": amount}

    @staticmethod
    def _raise_unexpected_order_response(response: object) -> None:
        status = int(getattr(response, "status", 0) or 0)
        if status in {200, 201, 400, 404}:
            return
        raise error_from_response(response)
