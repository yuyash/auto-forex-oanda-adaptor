"""Mapping between OANDA v20 objects and Core domain models."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from datetime import datetime
from decimal import Decimal
from typing import Any

from core import (
    AccountId,
    BrokerOrderId,
    BrokerPositionId,
    BrokerTradeId,
    BrokerTransactionId,
    Candle,
    Currency,
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
    PositionSideState,
    Tick,
)
from core.clock import local_timezone, now

from oanda.domain import (
    OandaAccount,
    OandaAccountSummary,
    OandaOrder,
    OandaPosition,
    OandaTrade,
    OandaTransaction,
)


class _MapperSupport:
    """Shared private conversion helpers for OANDA mapper classes."""

    @staticmethod
    def body(response: Any) -> Any:
        return getattr(response, "body", None) or {}

    @staticmethod
    def metadata(data: Any) -> Metadata:
        if hasattr(data, "model_dump"):
            return Metadata.model_validate(
                data.model_dump(mode="json", by_alias=True, exclude_none=True)
            )
        if isinstance(data, Mapping):
            return Metadata.model_validate(dict(data))
        values = {
            key: value
            for key in dir(data)
            if not key.startswith("_") and not callable(value := getattr(data, key))
        }
        return Metadata.model_validate(values)

    @classmethod
    def first(cls, data: Any, *keys: str) -> Any:
        for key in keys:
            value = cls.get(data, key)
            if value is not None:
                return value
        return None

    @classmethod
    def get(cls, data: Any, key: str, default: Any = None) -> Any:
        if data is None:
            return default
        if isinstance(data, Mapping):
            if key in data:
                return data[key]
            return data.get(cls.snake(key), default)
        if hasattr(data, key):
            return getattr(data, key)
        return getattr(data, cls.snake(key), default)

    @staticmethod
    def snake(name: str) -> str:
        value = name
        value = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", value)
        value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
        return value.lower()

    @staticmethod
    def decimal(value: Any) -> Decimal:
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))

    @staticmethod
    def parse_time(value: Any) -> datetime:
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

    @classmethod
    def average_candle_data(cls, bid: Any, ask: Any) -> dict[str, Decimal]:
        if bid is None or ask is None:
            msg = "OANDA candle must include mid data or both bid and ask data"
            raise ValueError(msg)
        return {
            key: (cls.decimal(cls.get(bid, key)) + cls.decimal(cls.get(ask, key))) / 2
            for key in ("o", "h", "l", "c")
        }


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
    def account_from_properties(item: Any) -> OandaAccount:
        """Convert OANDA account properties into a normalized account."""
        return OandaAccount(
            id=AccountId.of(str(_MapperSupport.get(item, "id"))),
            alias=_MapperSupport.get(item, "alias"),
            mt4_account_id=_MapperSupport.get(item, "mt4AccountID"),
            tags=tuple(_MapperSupport.get(item, "tags", ()) or ()),
        )

    @staticmethod
    def summary_from_response(response: Any) -> OandaAccountSummary:
        """Convert an OANDA account summary response into a normalized summary."""
        body = _MapperSupport.body(response)
        account = _MapperSupport.get(body, "account")
        currency = Currency.of(str(_MapperSupport.get(account, "currency")))
        return OandaAccountSummary(
            account_id=AccountId.of(str(_MapperSupport.get(account, "id"))),
            currency=currency,
            alias=_MapperSupport.get(account, "alias"),
            balance=Money.of(_MapperSupport.get(account, "balance"), currency),
            nav=Money.of(_MapperSupport.get(account, "NAV"), currency),
            margin_used=Money.of(_MapperSupport.get(account, "marginUsed"), currency),
            margin_available=Money.of(_MapperSupport.get(account, "marginAvailable"), currency),
            margin_rate=_MapperSupport.decimal(_MapperSupport.get(account, "marginRate"))
            if _MapperSupport.get(account, "marginRate") is not None
            else None,
            open_trade_count=_MapperSupport.get(account, "openTradeCount"),
            open_position_count=_MapperSupport.get(account, "openPositionCount"),
            pending_order_count=_MapperSupport.get(account, "pendingOrderCount"),
            last_transaction_id=_MapperSupport.get(body, "lastTransactionID"),
            created_at=_MapperSupport.parse_time(_MapperSupport.get(account, "createdTime"))
            if _MapperSupport.get(account, "createdTime") is not None
            else None,
            financing_mode=_MapperSupport.get(account, "financingMode"),
            hedging_enabled=_MapperSupport.get(account, "hedgingEnabled"),
            position_aggregation_mode=_MapperSupport.get(account, "positionAggregationMode"),
            guaranteed_stop_loss_order_mode=_MapperSupport.get(
                account, "guaranteedStopLossOrderMode"
            ),
            withdrawal_limit=_MapperSupport.decimal(_MapperSupport.get(account, "withdrawalLimit"))
            if _MapperSupport.get(account, "withdrawalLimit") is not None
            else None,
        )

    @staticmethod
    def account_currency_from_response(response: Any) -> Currency:
        """Return the account home currency from an account summary response."""
        account = _MapperSupport.get(_MapperSupport.body(response), "account")
        currency = _MapperSupport.get(account, "currency")
        if currency is None:
            msg = "OANDA account summary response does not include account currency"
            raise ValueError(msg)
        return Currency.of(str(currency))


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
        body = _MapperSupport.body(response)
        fill = _MapperSupport.first(body, "orderFillTransaction")
        cancel = _MapperSupport.first(body, "orderCancelTransaction")
        reject = _MapperSupport.first(
            body, "orderRejectTransaction", "orderReissueRejectTransaction"
        )
        create = _MapperSupport.first(body, "orderCreateTransaction")
        error_code = str(_MapperSupport.get(body, "errorCode", "") or "")

        status = self._status_from_transactions(
            response=response,
            fill=fill,
            cancel=cancel,
            reject=reject,
            create=create,
        )
        filled_units = (
            abs(_MapperSupport.decimal(_MapperSupport.get(fill, "units", "0")))
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
            related_transaction_ids=tuple(
                _MapperSupport.get(body, "relatedTransactionIDs", ()) or ()
            ),
            last_transaction_id=_MapperSupport.get(body, "lastTransactionID"),
            metadata=reason.details,
        )

    def metadata_from_order_response(self, response: Any) -> Metadata:
        """Return raw order response metadata for read-only order endpoints."""
        return _MapperSupport.metadata(_MapperSupport.body(response))

    def order_from_position_close_response(
        self,
        response: Any,
        *,
        position: Position,
        side: PositionSide,
        requested_units: Decimal,
    ) -> OandaOrder:
        """Convert a close-position response into a normalized OANDA order."""
        body = _MapperSupport.body(response)
        fill = _MapperSupport.first(body, "longOrderFillTransaction", "shortOrderFillTransaction")
        cancel = _MapperSupport.first(
            body, "longOrderCancelTransaction", "shortOrderCancelTransaction"
        )
        reject = _MapperSupport.first(
            body, "longOrderRejectTransaction", "shortOrderRejectTransaction"
        )
        create = _MapperSupport.first(
            body, "longOrderCreateTransaction", "shortOrderCreateTransaction"
        )
        error_code = str(_MapperSupport.get(body, "errorCode", "") or "")
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
            filled_units=abs(_MapperSupport.decimal(_MapperSupport.get(fill, "units", "0")))
            if fill is not None
            else Decimal("0"),
            average_fill_price=self._fill_price(fill, position.instrument),
            reason=reason,
            related_transaction_ids=tuple(
                _MapperSupport.get(body, "relatedTransactionIDs", ()) or ()
            ),
            last_transaction_id=_MapperSupport.get(body, "lastTransactionID"),
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
            value = _MapperSupport.get(transaction, "orderID") or _MapperSupport.get(
                transaction, "id"
            )
            if value:
                return BrokerOrderId.of(str(value))
        return None

    @staticmethod
    def _fill_price(fill: Any, instrument: CurrencyPair) -> Money | None:
        price = _MapperSupport.get(fill, "price")
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
        body = _MapperSupport.body(response)
        for key in ("errorCode", "errorMessage", "lastTransactionID", "relatedTransactionIDs"):
            value = _MapperSupport.get(body, key)
            if value is not None:
                details[key] = value
        for name, transaction in {
            "fill_transaction_id": fill,
            "cancel_transaction_id": cancel,
            "reject_transaction_id": reject,
            "create_transaction_id": create,
        }.items():
            value = _MapperSupport.get(transaction, "id")
            if value is not None:
                details[name] = value
        return Metadata.model_validate(details)


class OandaPositionMapper:
    """Map OANDA position objects into Core two-sided positions."""

    def __init__(self, *, account_currency: Currency | str) -> None:
        self.account_currency = Currency.of(account_currency)

    def positions_from_response(self, response: Any) -> tuple[OandaPosition, ...]:
        """Convert an OANDA positions response into Core positions."""
        body = _MapperSupport.body(response)
        positions = _MapperSupport.get(body, "positions", ()) or ()
        return tuple(
            position
            for item in positions
            if (position := self.position_from_oanda(item)) is not None
        )

    def position_from_oanda(self, item: Any) -> OandaPosition | None:
        """Convert a net OANDA position into one Core two-sided position."""
        instrument = CurrencyPair.of(str(_MapperSupport.get(item, "instrument")))
        long_state = self._position_side(
            instrument, PositionSide.LONG, _MapperSupport.get(item, "long")
        )
        short_state = self._position_side(
            instrument, PositionSide.SHORT, _MapperSupport.get(item, "short")
        )
        if long_state is None and short_state is None:
            return None
        return OandaPosition(
            instrument=instrument,
            long=long_state,
            short=short_state,
            unrealized_pl=self._unrealized_pl(item),
            pl=_MapperSupport.decimal(_MapperSupport.get(item, "pl"))
            if _MapperSupport.get(item, "pl") is not None
            else None,
            resettable_pl=_MapperSupport.decimal(_MapperSupport.get(item, "resettablePL"))
            if _MapperSupport.get(item, "resettablePL") is not None
            else None,
            financing=_MapperSupport.decimal(_MapperSupport.get(item, "financing"))
            if _MapperSupport.get(item, "financing") is not None
            else None,
            margin_used=_MapperSupport.decimal(_MapperSupport.get(item, "marginUsed"))
            if _MapperSupport.get(item, "marginUsed") is not None
            else None,
            long_trade_ids=tuple(
                _MapperSupport.get(_MapperSupport.get(item, "long"), "tradeIDs", ()) or ()
            ),
            short_trade_ids=tuple(
                _MapperSupport.get(_MapperSupport.get(item, "short"), "tradeIDs", ()) or ()
            ),
            metadata=Metadata.model_validate(
                {
                    "oanda_instrument": _MapperSupport.get(item, "instrument"),
                    "oanda_long_pl": _MapperSupport.get(_MapperSupport.get(item, "long"), "pl"),
                    "oanda_short_pl": _MapperSupport.get(_MapperSupport.get(item, "short"), "pl"),
                }
            ),
        )

    def _position_side(
        self,
        instrument: CurrencyPair,
        side: PositionSide,
        position_side: Any,
    ) -> PositionSideState | None:
        units = abs(_MapperSupport.decimal(_MapperSupport.get(position_side, "units", "0")))
        average_price = _MapperSupport.get(position_side, "averagePrice")
        if units == 0 or average_price is None:
            return None
        return PositionSideState(
            side=side,
            units=units,
            average_entry_price=Money.of(average_price, instrument.quote),
            broker_position_id=BrokerPositionId.of(f"{instrument.symbol}:{side.value}"),
            unrealized_pl=self._unrealized_pl(position_side),
            metadata=Metadata.model_validate(
                {
                    "oanda_trade_ids": tuple(
                        _MapperSupport.get(position_side, "tradeIDs", ()) or ()
                    ),
                    "oanda_pl": _MapperSupport.get(position_side, "pl"),
                    "oanda_resettable_pl": _MapperSupport.get(position_side, "resettablePL"),
                    "oanda_financing": _MapperSupport.get(position_side, "financing"),
                }
            ),
        )

    def _unrealized_pl(self, position_side: Any) -> Money | None:
        unrealized = _MapperSupport.get(position_side, "unrealizedPL")
        if unrealized is None:
            return None
        return Money.of(unrealized, self.account_currency)


class OandaTradeMapper:
    """Map OANDA trade objects into Core trade snapshots."""

    def __init__(self, *, account_currency: Currency | str) -> None:
        self.account_currency = Currency.of(account_currency)

    def trades_from_response(self, response: Any) -> tuple[OandaTrade, ...]:
        """Convert an OANDA trades response into Core trades."""
        trades = _MapperSupport.get(_MapperSupport.body(response), "trades", ()) or ()
        return tuple(self.trade_from_oanda(trade) for trade in trades)

    def trade_from_response(self, response: Any) -> OandaTrade:
        """Convert an OANDA trade response into one Core trade."""
        return self.trade_from_oanda(_MapperSupport.get(_MapperSupport.body(response), "trade"))

    def trade_from_oanda(self, item: Any) -> OandaTrade:
        """Convert one OANDA trade object into a Core trade."""
        instrument = CurrencyPair.of(str(_MapperSupport.get(item, "instrument")))
        current_units = _MapperSupport.decimal(
            _MapperSupport.get(item, "currentUnits", _MapperSupport.get(item, "initialUnits", "0"))
        )
        side = PositionSide.LONG if current_units >= 0 else PositionSide.SHORT
        price = _MapperSupport.get(item, "price")
        realized_pl = _MapperSupport.get(item, "realizedPL")
        unrealized_pl = _MapperSupport.get(item, "unrealizedPL")
        return OandaTrade(
            id=BrokerTradeId.of(str(_MapperSupport.get(item, "id"))),
            instrument=instrument,
            side=side,
            units=abs(current_units),
            price=Money.of(price, instrument.quote) if price is not None else None,
            open_time=_MapperSupport.parse_time(_MapperSupport.get(item, "openTime"))
            if _MapperSupport.get(item, "openTime")
            else None,
            close_time=_MapperSupport.parse_time(_MapperSupport.get(item, "closeTime"))
            if _MapperSupport.get(item, "closeTime")
            else None,
            state=str(_MapperSupport.get(item, "state", "open")).lower(),
            realized_pl=Money.of(realized_pl, self.account_currency)
            if realized_pl is not None
            else None,
            unrealized_pl=Money.of(unrealized_pl, self.account_currency)
            if unrealized_pl is not None
            else None,
            client_trade_id=_MapperSupport.get(_MapperSupport.get(item, "clientExtensions"), "id"),
            initial_units=abs(_MapperSupport.decimal(_MapperSupport.get(item, "initialUnits")))
            if _MapperSupport.get(item, "initialUnits") is not None
            else None,
            initial_margin_required=_MapperSupport.decimal(
                _MapperSupport.get(item, "initialMarginRequired")
            )
            if _MapperSupport.get(item, "initialMarginRequired") is not None
            else None,
            realized_pl_value=_MapperSupport.decimal(realized_pl)
            if realized_pl is not None
            else None,
            financing=_MapperSupport.decimal(_MapperSupport.get(item, "financing"))
            if _MapperSupport.get(item, "financing") is not None
            else None,
            dividend_adjustment=_MapperSupport.decimal(
                _MapperSupport.get(item, "dividendAdjustment")
            )
            if _MapperSupport.get(item, "dividendAdjustment") is not None
            else None,
            close_transaction_ids=tuple(
                _MapperSupport.get(item, "closingTransactionIDs", ()) or ()
            ),
            metadata=_MapperSupport.metadata(item),
        )


class OandaTransactionMapper:
    """Map OANDA transaction objects into Core transaction snapshots."""

    def __init__(self, *, account_currency: Currency | str) -> None:
        self.account_currency = Currency.of(account_currency)

    def transaction_from_response(self, response: Any) -> OandaTransaction:
        """Convert an OANDA transaction response into one Core transaction."""
        return self.transaction_from_oanda(
            _MapperSupport.get(_MapperSupport.body(response), "transaction")
        )

    def transactions_from_response(self, response: Any) -> tuple[OandaTransaction, ...]:
        """Convert an OANDA transactions response into Core transactions."""
        transactions = _MapperSupport.get(_MapperSupport.body(response), "transactions", ()) or ()
        return tuple(self.transaction_from_oanda(item) for item in transactions)

    def transaction_from_oanda(self, item: Any) -> OandaTransaction:
        """Convert one OANDA transaction into a Core transaction."""
        instrument = _MapperSupport.get(item, "instrument")
        account_id = _MapperSupport.get(item, "accountID")
        order_id = _MapperSupport.get(item, "orderID")
        amount = _MapperSupport.first(item, "amount", "pl", "financing", "commission")
        return OandaTransaction(
            id=BrokerTransactionId.of(str(_MapperSupport.get(item, "id"))),
            account_id=AccountId.of(str(account_id)) if account_id is not None else None,
            time=_MapperSupport.parse_time(_MapperSupport.get(item, "time"))
            if _MapperSupport.get(item, "time") is not None
            else None,
            type=str(_MapperSupport.get(item, "type", "UNKNOWN")),
            instrument=CurrencyPair.of(str(instrument)) if instrument is not None else None,
            order_id=BrokerOrderId.of(str(order_id)) if order_id is not None else None,
            amount=Money.of(amount, self.account_currency) if amount is not None else None,
            user_id=_MapperSupport.get(item, "userID"),
            batch_id=_MapperSupport.get(item, "batchID"),
            request_id=_MapperSupport.get(item, "requestID"),
            reason=_MapperSupport.get(item, "reason"),
            reject_reason=_MapperSupport.get(item, "rejectReason"),
            related_transaction_ids=tuple(
                _MapperSupport.get(item, "relatedTransactionIDs", ()) or ()
            ),
            metadata=_MapperSupport.metadata(item),
        )


class OandaMarketDataMapper:
    """Map OANDA price and candle objects into Core market data models."""

    def tick_from_price(self, price: Any) -> Tick:
        """Convert an OANDA ClientPrice/Price object into a Core tick."""
        instrument = CurrencyPair.of(str(_MapperSupport.get(price, "instrument")))
        bids = tuple(_MapperSupport.get(price, "bids", ()) or ())
        asks = tuple(_MapperSupport.get(price, "asks", ()) or ())
        if not bids or not asks:
            msg = f"OANDA price for {instrument} does not contain bid/ask liquidity"
            raise ValueError(msg)
        bid = _MapperSupport.get(bids[0], "price")
        ask = _MapperSupport.get(asks[0], "price")
        return Tick(
            instrument=instrument,
            timestamp=_MapperSupport.parse_time(_MapperSupport.get(price, "time")),
            bid=Money.of(bid, instrument.quote),
            ask=Money.of(ask, instrument.quote),
            metadata=Metadata.model_validate(
                {
                    "oanda_status": _MapperSupport.get(price, "status"),
                    "oanda_tradeable": _MapperSupport.get(price, "tradeable"),
                    "oanda_closeout_bid": _MapperSupport.get(price, "closeoutBid"),
                    "oanda_closeout_ask": _MapperSupport.get(price, "closeoutAsk"),
                }
            ),
        )

    def ticks_from_prices(self, prices: Iterable[Any]) -> tuple[Tick, ...]:
        """Convert OANDA price objects into Core ticks."""
        return tuple(self.tick_from_price(price) for price in prices)

    def candle_from_oanda(self, item: Any, *, instrument: CurrencyPair, granularity: str) -> Candle:
        """Convert an OANDA candlestick into a Core candle."""
        data = _MapperSupport.get(item, "mid")
        if data is None:
            bid = _MapperSupport.get(item, "bid")
            ask = _MapperSupport.get(item, "ask")
            data = _MapperSupport.average_candle_data(bid, ask)
        return Candle(
            instrument=instrument,
            timestamp=_MapperSupport.parse_time(_MapperSupport.get(item, "time")),
            granularity=granularity,
            open=Money.of(_MapperSupport.get(data, "o"), instrument.quote),
            high=Money.of(_MapperSupport.get(data, "h"), instrument.quote),
            low=Money.of(_MapperSupport.get(data, "l"), instrument.quote),
            close=Money.of(_MapperSupport.get(data, "c"), instrument.quote),
            volume=int(_MapperSupport.get(item, "volume", 0) or 0),
            complete=bool(_MapperSupport.get(item, "complete", True)),
            metadata=Metadata.model_validate(
                {"oanda_complete": _MapperSupport.get(item, "complete", True)}
            ),
        )

    def candles_from_response(
        self,
        response: Any,
        *,
        instrument: CurrencyPair,
        granularity: str,
    ) -> tuple[Candle, ...]:
        """Convert a candles response into Core candles."""
        candles = _MapperSupport.get(_MapperSupport.body(response), "candles", ()) or ()
        return tuple(
            self.candle_from_oanda(item, instrument=instrument, granularity=granularity)
            for item in candles
        )
