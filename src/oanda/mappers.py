"""Mapping between OANDA v20 objects and Core domain models."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from decimal import Decimal
from typing import Any

from core import (
    BrokerOrderId,
    BrokerPositionId,
    Candle,
    Currency,
    CurrencyPair,
    Metadata,
    Money,
    OrderRequest,
    OrderResult,
    OrderResultReason,
    OrderResultReasonCode,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    PositionSide,
    Tick,
)
from core.clock import local_timezone, now


class OandaInstrumentMapper:
    """Convert between Core and OANDA instrument representations."""

    @staticmethod
    def to_oanda(instrument: CurrencyPair) -> str:
        """Return the OANDA instrument name."""
        return instrument.symbol

    @staticmethod
    def to_core(instrument: str) -> CurrencyPair:
        """Return the Core currency pair."""
        return CurrencyPair.of(instrument)


class OandaAccountMapper:
    """Map OANDA account objects into Core value objects."""

    @staticmethod
    def account_currency_from_response(response: Any) -> Currency:
        """Return the account home currency from an account summary response."""
        account = _get(_body(response), "account")
        currency = _get(account, "currency")
        if currency is None:
            msg = "OANDA account summary response does not include account currency"
            raise ValueError(msg)
        return Currency.of(str(currency))


class OandaOrderMapper:
    """Map Core order requests and OANDA responses."""

    def order_kwargs(self, request: OrderRequest) -> dict[str, Any]:
        """Convert a Core order request into v20 order kwargs."""
        units = self._signed_units(request)
        base: dict[str, Any] = {
            "instrument": OandaInstrumentMapper.to_oanda(request.instrument),
            "units": str(units),
            "positionFill": "DEFAULT",
            "clientExtensions": {
                "id": str(request.request_id),
                "tag": "auto-forex",
            },
        }

        if request.order_type == OrderType.MARKET:
            return {**base, "timeInForce": "FOK"}

        if request.price is None:
            msg = f"{request.order_type.value} order requires price"
            raise ValueError(msg)

        priced = {
            **base,
            "price": str(request.price.require_currency(request.instrument.quote).amount),
            "timeInForce": "GTC",
        }
        if request.order_type in {OrderType.LIMIT, OrderType.STOP}:
            return priced

        msg = f"unsupported order type: {request.order_type}"
        raise ValueError(msg)

    def result_from_order_response(self, response: Any, request: OrderRequest) -> OrderResult:
        """Convert a create-order response into a Core order result."""
        body = _body(response)
        fill = _first(body, "orderFillTransaction")
        cancel = _first(body, "orderCancelTransaction")
        reject = _first(body, "orderRejectTransaction", "orderReissueRejectTransaction")
        create = _first(body, "orderCreateTransaction")
        error_code = str(_get(body, "errorCode", "") or "")

        status = self._status_from_transactions(
            response=response,
            fill=fill,
            cancel=cancel,
            reject=reject,
            create=create,
        )
        filled_units = abs(_decimal(_get(fill, "units", "0"))) if fill is not None else Decimal("0")
        average_fill_price = self._fill_price(fill, request.instrument)
        broker_order_id = self._broker_order_id(fill, create, cancel, reject)
        reason = OrderResultReason(
            code=self._reason_code(status=status, error_code=error_code),
            details=self._result_details(response, fill, cancel, reject, create),
        )

        return OrderResult(
            status=status,
            broker_order_id=broker_order_id,
            instrument=request.instrument,
            side=request.side,
            requested_units=request.units,
            filled_units=filled_units,
            average_fill_price=average_fill_price,
            reason=reason,
            metadata=reason.details,
        )

    def result_from_position_close_response(
        self,
        response: Any,
        *,
        position: Position,
        requested_units: Decimal,
    ) -> OrderResult:
        """Convert a close-position response into a Core order result."""
        body = _body(response)
        fill = _first(body, "longOrderFillTransaction", "shortOrderFillTransaction")
        cancel = _first(body, "longOrderCancelTransaction", "shortOrderCancelTransaction")
        reject = _first(body, "longOrderRejectTransaction", "shortOrderRejectTransaction")
        create = _first(body, "longOrderCreateTransaction", "shortOrderCreateTransaction")
        error_code = str(_get(body, "errorCode", "") or "")
        status = self._status_from_transactions(
            response=response,
            fill=fill,
            cancel=cancel,
            reject=reject,
            create=create,
        )
        reason = OrderResultReason(
            code=self._reason_code(status=status, error_code=error_code),
            details=self._result_details(response, fill, cancel, reject, create),
        )
        return OrderResult(
            status=status,
            broker_order_id=self._broker_order_id(fill, create, cancel, reject),
            instrument=position.instrument,
            side=OrderSide.SELL if position.side == PositionSide.LONG else OrderSide.BUY,
            requested_units=requested_units,
            filled_units=abs(_decimal(_get(fill, "units", "0")))
            if fill is not None
            else Decimal("0"),
            average_fill_price=self._fill_price(fill, position.instrument),
            reason=reason,
            metadata=reason.details,
        )

    @staticmethod
    def _signed_units(request: OrderRequest) -> Decimal:
        units = request.units.copy_abs()
        return units if request.side == OrderSide.BUY else -units

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
            value = _get(transaction, "orderID") or _get(transaction, "id")
            if value:
                return BrokerOrderId.of(str(value))
        return None

    @staticmethod
    def _fill_price(fill: Any, instrument: CurrencyPair) -> Money | None:
        price = _get(fill, "price")
        if price is None:
            return None
        return Money.of(price, instrument.quote)

    @staticmethod
    def _reason_code(*, status: OrderStatus, error_code: str) -> OrderResultReasonCode:
        normalized = error_code.upper()
        if "INSUFFICIENT_MARGIN" in normalized:
            return OrderResultReasonCode.INSUFFICIENT_MARGIN
        if "INSTRUMENT" in normalized:
            return OrderResultReasonCode.INVALID_INSTRUMENT
        if "PRICE" in normalized:
            return OrderResultReasonCode.INVALID_PRICE
        if "UNITS" in normalized:
            return OrderResultReasonCode.INVALID_UNITS
        if "MARKET_HALTED" in normalized or "MARKET_CLOSED" in normalized:
            return OrderResultReasonCode.MARKET_CLOSED
        if "RATE" in normalized:
            return OrderResultReasonCode.RATE_LIMITED
        if "TIMEOUT" in normalized:
            return OrderResultReasonCode.TIMEOUT
        if status == OrderStatus.FILLED:
            return OrderResultReasonCode.FILLED
        if status == OrderStatus.ACCEPTED:
            return OrderResultReasonCode.ACCEPTED
        if status == OrderStatus.CANCELLED:
            return OrderResultReasonCode.CANCELLED
        if status == OrderStatus.REJECTED:
            return OrderResultReasonCode.BROKER_REJECTED
        return OrderResultReasonCode.UNKNOWN

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
        body = _body(response)
        for key in ("errorCode", "errorMessage", "lastTransactionID", "relatedTransactionIDs"):
            value = _get(body, key)
            if value is not None:
                details[key] = value
        for name, transaction in {
            "fill_transaction_id": fill,
            "cancel_transaction_id": cancel,
            "reject_transaction_id": reject,
            "create_transaction_id": create,
        }.items():
            value = _get(transaction, "id")
            if value is not None:
                details[name] = value
        return Metadata.model_validate(details)


class OandaPositionMapper:
    """Map OANDA position objects into Core position side snapshots."""

    def __init__(self, *, account_currency: Currency | str) -> None:
        self.account_currency = Currency.of(account_currency)

    def positions_from_response(self, response: Any) -> tuple[Position, ...]:
        """Convert an OANDA positions response into Core positions."""
        body = _body(response)
        positions = _get(body, "positions", ()) or ()
        return tuple(position for item in positions for position in self.positions_from_oanda(item))

    def positions_from_oanda(self, item: Any) -> tuple[Position, ...]:
        """Convert a net OANDA position into zero, one, or two Core positions."""
        instrument = CurrencyPair.of(str(_get(item, "instrument")))
        positions: list[Position] = []
        long_position = self._position_side(item, instrument, PositionSide.LONG, _get(item, "long"))
        short_position = self._position_side(
            item, instrument, PositionSide.SHORT, _get(item, "short")
        )
        if long_position is not None:
            positions.append(long_position)
        if short_position is not None:
            positions.append(short_position)
        return tuple(positions)

    def _position_side(
        self,
        item: Any,
        instrument: CurrencyPair,
        side: PositionSide,
        position_side: Any,
    ) -> Position | None:
        units = abs(_decimal(_get(position_side, "units", "0")))
        average_price = _get(position_side, "averagePrice")
        if units == 0 or average_price is None:
            return None
        return Position(
            instrument=instrument,
            side=side,
            units=units,
            average_entry_price=Money.of(average_price, instrument.quote),
            broker_position_id=BrokerPositionId.of(f"{instrument.symbol}:{side.value}"),
            unrealized_pl=self._unrealized_pl(position_side),
            metadata=Metadata.model_validate(
                {
                    "oanda_instrument": _get(item, "instrument"),
                    "oanda_trade_ids": tuple(_get(position_side, "tradeIDs", ()) or ()),
                    "oanda_pl": _get(position_side, "pl"),
                    "oanda_resettable_pl": _get(position_side, "resettablePL"),
                    "oanda_financing": _get(position_side, "financing"),
                }
            ),
        )

    def _unrealized_pl(self, position_side: Any) -> Money | None:
        unrealized = _get(position_side, "unrealizedPL")
        if unrealized is None:
            return None
        return Money.of(unrealized, self.account_currency)


class OandaMarketDataMapper:
    """Map OANDA price and candle objects into Core market data models."""

    def tick_from_price(self, price: Any) -> Tick:
        """Convert an OANDA ClientPrice/Price object into a Core tick."""
        instrument = CurrencyPair.of(str(_get(price, "instrument")))
        bids = tuple(_get(price, "bids", ()) or ())
        asks = tuple(_get(price, "asks", ()) or ())
        if not bids or not asks:
            msg = f"OANDA price for {instrument} does not contain bid/ask liquidity"
            raise ValueError(msg)
        bid = _get(bids[0], "price")
        ask = _get(asks[0], "price")
        return Tick(
            instrument=instrument,
            timestamp=_parse_time(_get(price, "time")),
            bid=Money.of(bid, instrument.quote),
            ask=Money.of(ask, instrument.quote),
            metadata=Metadata.model_validate(
                {
                    "oanda_status": _get(price, "status"),
                    "oanda_tradeable": _get(price, "tradeable"),
                    "oanda_closeout_bid": _get(price, "closeoutBid"),
                    "oanda_closeout_ask": _get(price, "closeoutAsk"),
                }
            ),
        )

    def ticks_from_prices(self, prices: Iterable[Any]) -> tuple[Tick, ...]:
        """Convert OANDA price objects into Core ticks."""
        return tuple(self.tick_from_price(price) for price in prices)

    def candle_from_oanda(self, item: Any, *, instrument: CurrencyPair, granularity: str) -> Candle:
        """Convert an OANDA candlestick into a Core candle."""
        data = _get(item, "mid")
        if data is None:
            bid = _get(item, "bid")
            ask = _get(item, "ask")
            data = _average_candle_data(bid, ask)
        return Candle(
            instrument=instrument,
            timestamp=_parse_time(_get(item, "time")),
            granularity=granularity,
            open=Money.of(_get(data, "o"), instrument.quote),
            high=Money.of(_get(data, "h"), instrument.quote),
            low=Money.of(_get(data, "l"), instrument.quote),
            close=Money.of(_get(data, "c"), instrument.quote),
            volume=int(_get(item, "volume", 0) or 0),
            complete=bool(_get(item, "complete", True)),
            metadata=Metadata.model_validate({"oanda_complete": _get(item, "complete", True)}),
        )

    def candles_from_response(
        self,
        response: Any,
        *,
        instrument: CurrencyPair,
        granularity: str,
    ) -> tuple[Candle, ...]:
        """Convert a candles response into Core candles."""
        candles = _get(_body(response), "candles", ()) or ()
        return tuple(
            self.candle_from_oanda(item, instrument=instrument, granularity=granularity)
            for item in candles
        )


def _body(response: Any) -> Any:
    return getattr(response, "body", None) or {}


def _first(data: Any, *keys: str) -> Any:
    for key in keys:
        value = _get(data, key)
        if value is not None:
            return value
    return None


def _get(data: Any, key: str, default: Any = None) -> Any:
    if data is None:
        return default
    if isinstance(data, Mapping):
        return data.get(key, default)
    return getattr(data, key, default)


def _decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _parse_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=local_timezone())
        return value
    if value is None:
        return now()
    text = str(value)
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    if "." in text:
        prefix, suffix = text.split(".", 1)
        fraction = suffix
        timezone = ""
        for separator in ("+", "-"):
            if separator in suffix:
                fraction, timezone = suffix.split(separator, 1)
                timezone = f"{separator}{timezone}"
                break
        text = f"{prefix}.{fraction[:6].ljust(6, '0')}{timezone}"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=local_timezone())
    return parsed


def _average_candle_data(bid: Any, ask: Any) -> dict[str, Decimal]:
    if bid is None or ask is None:
        msg = "OANDA candle must include mid data or both bid and ask data"
        raise ValueError(msg)
    return {
        key: (_decimal(_get(bid, key)) + _decimal(_get(ask, key))) / 2
        for key in ("o", "h", "l", "c")
    }
