"""Trade mapping between OANDA payloads and Core domain models."""

from __future__ import annotations

from core import BrokerTradeId, Currency, CurrencyPair, Money, PositionSide, Trade

import oanda.models as om
import oanda.payload as payload
from oanda.converters import trade_to_core
from oanda.snapshots import OandaTrade


class OandaTradeMapper:
    """Map OANDA trade objects into Core trade snapshots."""

    def __init__(self, *, account_currency: Currency) -> None:
        self.account_currency = account_currency

    def trades_from_response(
        self, response: om.OandaResponse[om.TradesResponse]
    ) -> tuple[Trade, ...]:
        """Convert an OANDA trades response into Core trades."""
        trades = payload.get(payload.body(response), "trades", ()) or ()
        return tuple(self.trade_from_oanda(trade) for trade in trades)

    def trade_from_response(self, response: om.OandaResponse[om.TradeResponse]) -> Trade:
        """Convert an OANDA trade response into one Core trade."""
        return self.trade_from_oanda(payload.get(payload.body(response), "trade"))

    def trade_from_oanda(self, item: object) -> Trade:
        """Convert one OANDA trade object into a Core trade."""
        instrument = CurrencyPair.of(str(payload.get(item, "instrument")))
        current_units = payload.decimal(
            payload.get(item, "currentUnits", payload.get(item, "initialUnits", "0"))
        )
        side = PositionSide.LONG if current_units >= 0 else PositionSide.SHORT
        price = payload.get(item, "price")
        realized_pl = payload.get(item, "realizedPL")
        unrealized_pl = payload.get(item, "unrealizedPL")
        trade = Trade(
            id=BrokerTradeId.of(str(payload.get(item, "id"))),
            instrument=instrument,
            side=side,
            units=abs(current_units),
            price=Money.of(price, instrument.quote) if price is not None else None,
            open_time=payload.parse_time(payload.get(item, "openTime"))
            if payload.get(item, "openTime")
            else None,
            close_time=payload.parse_time(payload.get(item, "closeTime"))
            if payload.get(item, "closeTime")
            else None,
            state=str(payload.get(item, "state", "open")).lower(),
            realized_pl=Money.of(realized_pl, self.account_currency)
            if realized_pl is not None
            else None,
            unrealized_pl=Money.of(unrealized_pl, self.account_currency)
            if unrealized_pl is not None
            else None,
            metadata=payload.metadata(item),
        )
        return trade_to_core(
            OandaTrade(
                trade=trade,
                client_trade_id=payload.get(payload.get(item, "clientExtensions"), "id"),
                initial_units=abs(payload.decimal(payload.get(item, "initialUnits")))
                if payload.get(item, "initialUnits") is not None
                else None,
                initial_margin_required=payload.decimal(payload.get(item, "initialMarginRequired"))
                if payload.get(item, "initialMarginRequired") is not None
                else None,
                realized_pl_value=payload.decimal(realized_pl) if realized_pl is not None else None,
                financing=payload.decimal(payload.get(item, "financing"))
                if payload.get(item, "financing") is not None
                else None,
                dividend_adjustment=payload.decimal(payload.get(item, "dividendAdjustment"))
                if payload.get(item, "dividendAdjustment") is not None
                else None,
                close_transaction_ids=tuple(payload.get(item, "closingTransactionIDs", ()) or ()),
            )
        )
