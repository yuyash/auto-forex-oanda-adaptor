"""Mapping between OANDA v20 objects and Core domain models.

This module keeps the historical public import path while mapper
implementations live in smaller domain-specific modules.
"""

from __future__ import annotations

from oanda.mappers.account import OandaAccountMapper
from oanda.mappers.instrument import OandaInstrumentMapper
from oanda.mappers.market_data import OandaMarketDataMapper
from oanda.mappers.order import OandaOrderMapper
from oanda.mappers.position import OandaPositionMapper
from oanda.mappers.trade import OandaTradeMapper
from oanda.mappers.transaction import OandaTransactionMapper

__all__ = [
    "OandaAccountMapper",
    "OandaInstrumentMapper",
    "OandaMarketDataMapper",
    "OandaOrderMapper",
    "OandaPositionMapper",
    "OandaTradeMapper",
    "OandaTransactionMapper",
]
