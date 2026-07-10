from __future__ import annotations

from core import CurrencyPair

from oanda import OandaProvider, OandaSettings
from oanda.models import OandaStreamResponse


class TestBrokerLiveReadonly:
    def test_live_broker_order_trade_position_and_transaction_readonly_apis(
        self,
        oanda_provider: OandaProvider,
        oanda_settings: OandaSettings,
        e2e_instrument: CurrencyPair,
    ) -> None:
        orders = oanda_provider.broker.list_orders(count=10)
        pending_orders = oanda_provider.broker.list_pending_orders()
        positions = oanda_provider.broker.list_positions()
        open_positions = oanda_provider.broker.list_open_positions()
        trades = oanda_provider.broker.list_trades(count=10)
        open_trades = oanda_provider.broker.list_open_trades()
        transaction_page = oanda_provider.broker.list_transactions(page_size=100)
        last_transaction_id = str(transaction_page["lastTransactionID"])
        transaction = oanda_provider.broker.get_transaction(last_transaction_id)
        ranged = oanda_provider.broker.get_transaction_range(
            from_id=last_transaction_id,
            to_id=last_transaction_id,
        )
        since = oanda_provider.broker.get_transactions_since(last_transaction_id)

        assert isinstance(orders, tuple)
        assert isinstance(pending_orders, tuple)
        assert isinstance(positions, tuple)
        assert isinstance(open_positions, tuple)
        assert isinstance(trades, tuple)
        assert isinstance(open_trades, tuple)
        assert transaction.id.value == last_transaction_id
        assert ranged
        assert isinstance(since, tuple)

        if open_positions:
            fetched_position = oanda_provider.broker.get_position(open_positions[0].instrument)
            assert fetched_position.instrument == open_positions[0].instrument
        else:
            instrument_positions = tuple(
                item for item in positions if item.instrument == e2e_instrument
            )
            assert isinstance(instrument_positions, tuple)

        if open_trades:
            fetched_trade = oanda_provider.broker.get_trade(open_trades[0].id.value)
            assert fetched_trade.id == open_trades[0].id

        assert oanda_settings.account_id

    def test_live_transaction_stream_endpoint_connects(
        self,
        oanda_provider: OandaProvider,
        oanda_settings: OandaSettings,
    ) -> None:
        broker = oanda_provider.broker
        response = broker.gateway.stream_transactions(oanda_settings.account_id)
        try:
            assert response.status == 200
            assert isinstance(response.raw, OandaStreamResponse)
            assert response.raw.stream_kind == "transactions"
        finally:
            close = getattr(response.raw.stream, "close", None)
            if close is not None:
                close()
