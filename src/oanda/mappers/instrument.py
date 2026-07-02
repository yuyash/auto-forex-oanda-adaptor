"""Instrument mapping helpers."""

from __future__ import annotations

from core import CurrencyPair


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
