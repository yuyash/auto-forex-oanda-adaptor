"""Facade for OANDA REST v20 endpoint clients."""

from __future__ import annotations

from typing import Any

import oanda.models as om
from oanda.config import OandaSettings
from oanda.gateways.clients import (
    OandaAccountsApi,
    OandaOrdersApi,
    OandaPositionsApi,
    OandaPricingApi,
    OandaTradesApi,
    OandaTransactionsApi,
)
from oanda.transport import OandaRetryPolicy, OandaTransport


class OandaGateway:
    """Compatibility facade for the OANDA REST v20 API."""

    def __init__(
        self,
        *,
        access_token: str,
        hostname: str,
        stream_hostname: str,
        port: int = 443,
        ssl: bool = True,
        application: str = "AutoForexV2",
        poll_timeout: int = 10,
        stream_timeout: int = 60,
        retry_policy: OandaRetryPolicy | None = None,
        opener: Any | None = None,
        transport: OandaTransport | None = None,
    ) -> None:
        self.transport = transport or OandaTransport(
            access_token=access_token,
            hostname=hostname,
            stream_hostname=stream_hostname,
            port=port,
            ssl=ssl,
            application=application,
            poll_timeout=poll_timeout,
            stream_timeout=stream_timeout,
            retry_policy=retry_policy,
            opener=opener,
        )
        self.accounts = OandaAccountsApi(self.transport)
        self.orders = OandaOrdersApi(self.transport)
        self.positions = OandaPositionsApi(self.transport)
        self.pricing = OandaPricingApi(self.transport)
        self.trades = OandaTradesApi(self.transport)
        self.transactions = OandaTransactionsApi(self.transport)

    @classmethod
    def from_settings(cls, settings: OandaSettings) -> OandaGateway:
        """Create a gateway from OANDA settings."""
        return cls(
            access_token=settings.access_token.get_secret_value(),
            hostname=settings.resolved_hostname,
            stream_hostname=settings.resolved_stream_hostname,
            port=settings.port,
            ssl=settings.ssl,
            application=settings.application,
            stream_timeout=settings.stream_timeout,
            poll_timeout=settings.poll_timeout,
            retry_policy=OandaRetryPolicy.from_settings(settings),
        )

    @property
    def access_token(self) -> str:
        """Return the configured OANDA access token."""
        return self.transport.access_token

    @property
    def hostname(self) -> str:
        """Return the REST API hostname."""
        return self.transport.hostname

    @property
    def stream_hostname(self) -> str:
        """Return the streaming API hostname."""
        return self.transport.stream_hostname

    @property
    def port(self) -> int:
        """Return the API port."""
        return self.transport.port

    @property
    def ssl(self) -> bool:
        """Return whether HTTPS is enabled."""
        return self.transport.ssl

    @property
    def application(self) -> str:
        """Return the User-Agent application name."""
        return self.transport.application

    @property
    def poll_timeout(self) -> int:
        """Return the non-streaming request timeout."""
        return self.transport.poll_timeout

    @property
    def stream_timeout(self) -> int:
        """Return the streaming request timeout."""
        return self.transport.stream_timeout

    @property
    def retry_policy(self) -> OandaRetryPolicy:
        """Return the retry policy."""
        return self.transport.retry_policy

    @property
    def opener(self) -> Any:
        """Return the underlying urllib opener."""
        return self.transport.opener

    def datetime_to_str(self, value: Any) -> str:
        """Format a datetime value for OANDA query parameters."""
        return self.transport.datetime_to_str(value)

    def request(
        self,
        method: str,
        path: str,
        *,
        query: Any = None,
        body: Any = None,
        retry: bool = False,
    ) -> om.OandaResponse[dict[str, Any]]:
        """Execute a raw REST request and return a typed response wrapper."""
        return self.transport.request(method, path, query=query, body=body, retry=retry)

    def list_accounts(self) -> om.OandaResponse[om.AccountsResponse]:
        """List accounts authorized for the token."""
        return self.accounts.list_accounts()

    def get_account(self, account_id: str) -> om.OandaResponse[om.AccountResponse]:
        """Get full account details."""
        return self.accounts.get_account(account_id)

    def get_account_summary(self, account_id: str) -> om.OandaResponse[om.AccountSummaryResponse]:
        """Get account summary."""
        return self.accounts.get_account_summary(account_id)

    def get_account_instruments(
        self,
        account_id: str,
        request: om.AccountInstrumentsRequest | None = None,
    ) -> om.OandaResponse[om.AccountInstrumentsResponse]:
        """Get account tradable instruments."""
        return self.accounts.get_account_instruments(account_id, request)

    def configure_account(
        self,
        account_id: str,
        request: om.ConfigureAccountRequest | None = None,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.ConfigureAccountResponse]:
        """Configure account alias or margin settings."""
        return self.accounts.configure_account(account_id, request, retry=retry, **kwargs)

    def get_account_changes(
        self,
        account_id: str,
        request: om.AccountChangesRequest | None = None,
    ) -> om.OandaResponse[om.AccountChangesResponse]:
        """Get account changes since a transaction ID."""
        return self.accounts.get_account_changes(account_id, request)

    def create_order(
        self,
        account_id: str,
        request: om.CreateOrderRequest | None = None,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.OrderTransactionResponse]:
        """Create an order."""
        return self.orders.create_order(account_id, request, retry=retry, **kwargs)

    def list_orders(
        self,
        account_id: str,
        request: om.OrdersRequest | None = None,
    ) -> om.OandaResponse[om.OrdersResponse]:
        """List orders."""
        return self.orders.list_orders(account_id, request)

    def list_pending_orders(self, account_id: str) -> om.OandaResponse[om.OrdersResponse]:
        """List pending orders."""
        return self.orders.list_pending_orders(account_id)

    def get_order(
        self, account_id: str, order_specifier: str
    ) -> om.OandaResponse[om.OrderResponse]:
        """Get one order."""
        return self.orders.get_order(account_id, order_specifier)

    def replace_order(
        self,
        account_id: str,
        order_specifier: str,
        request: om.ReplaceOrderRequest | None = None,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.OrderTransactionResponse]:
        """Replace one order."""
        return self.orders.replace_order(
            account_id, order_specifier, request, retry=retry, **kwargs
        )

    def cancel_order(
        self,
        account_id: str,
        order_specifier: str,
        *,
        retry: bool = False,
    ) -> om.OandaResponse[om.OrderTransactionResponse]:
        """Cancel one order."""
        return self.orders.cancel_order(account_id, order_specifier, retry=retry)

    def set_order_client_extensions(
        self,
        account_id: str,
        order_specifier: str,
        request: om.SetOrderClientExtensionsRequest | None = None,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.OrderTransactionResponse]:
        """Set order client extensions."""
        return self.orders.set_order_client_extensions(
            account_id, order_specifier, request, retry=retry, **kwargs
        )

    def create_market_order(
        self,
        account_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.OrderTransactionResponse]:
        """Create a market order."""
        return self.orders.create_market_order(account_id, retry=retry, **kwargs)

    def create_limit_order(
        self,
        account_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.OrderTransactionResponse]:
        """Create a limit order."""
        return self.orders.create_limit_order(account_id, retry=retry, **kwargs)

    def replace_limit_order(
        self,
        account_id: str,
        order_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.OrderTransactionResponse]:
        """Replace a limit order."""
        return self.orders.replace_limit_order(account_id, order_id, retry=retry, **kwargs)

    def create_stop_order(
        self,
        account_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.OrderTransactionResponse]:
        """Create a stop order."""
        return self.orders.create_stop_order(account_id, retry=retry, **kwargs)

    def replace_stop_order(
        self,
        account_id: str,
        order_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.OrderTransactionResponse]:
        """Replace a stop order."""
        return self.orders.replace_stop_order(account_id, order_id, retry=retry, **kwargs)

    def create_market_if_touched_order(
        self,
        account_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.OrderTransactionResponse]:
        """Create a market-if-touched order."""
        return self.orders.create_market_if_touched_order(account_id, retry=retry, **kwargs)

    def replace_market_if_touched_order(
        self,
        account_id: str,
        order_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.OrderTransactionResponse]:
        """Replace a market-if-touched order."""
        return self.orders.replace_market_if_touched_order(
            account_id, order_id, retry=retry, **kwargs
        )

    def create_take_profit_order(
        self,
        account_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.OrderTransactionResponse]:
        """Create a take-profit order."""
        return self.orders.create_take_profit_order(account_id, retry=retry, **kwargs)

    def replace_take_profit_order(
        self,
        account_id: str,
        order_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.OrderTransactionResponse]:
        """Replace a take-profit order."""
        return self.orders.replace_take_profit_order(account_id, order_id, retry=retry, **kwargs)

    def create_stop_loss_order(
        self,
        account_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.OrderTransactionResponse]:
        """Create a stop-loss order."""
        return self.orders.create_stop_loss_order(account_id, retry=retry, **kwargs)

    def replace_stop_loss_order(
        self,
        account_id: str,
        order_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.OrderTransactionResponse]:
        """Replace a stop-loss order."""
        return self.orders.replace_stop_loss_order(account_id, order_id, retry=retry, **kwargs)

    def create_trailing_stop_loss_order(
        self,
        account_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.OrderTransactionResponse]:
        """Create a trailing stop-loss order."""
        return self.orders.create_trailing_stop_loss_order(account_id, retry=retry, **kwargs)

    def replace_trailing_stop_loss_order(
        self,
        account_id: str,
        order_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.OrderTransactionResponse]:
        """Replace a trailing stop-loss order."""
        return self.orders.replace_trailing_stop_loss_order(
            account_id, order_id, retry=retry, **kwargs
        )

    def list_positions(self, account_id: str) -> om.OandaResponse[om.PositionsResponse]:
        """List positions."""
        return self.positions.list_positions(account_id)

    def list_open_positions(self, account_id: str) -> om.OandaResponse[om.PositionsResponse]:
        """List open positions."""
        return self.positions.list_open_positions(account_id)

    def get_position(
        self, account_id: str, instrument: str
    ) -> om.OandaResponse[om.PositionResponse]:
        """Get one position."""
        return self.positions.get_position(account_id, instrument)

    def close_position(
        self,
        account_id: str,
        instrument: str,
        request: om.ClosePositionRequest | None = None,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.PositionCloseResponse]:
        """Close one position."""
        return self.positions.close_position(account_id, instrument, request, retry=retry, **kwargs)

    def get_account_prices(
        self,
        account_id: str,
        request: om.PricingRequest | None = None,
        **kwargs: Any,
    ) -> om.OandaResponse[om.PricingResponse]:
        """Get account prices."""
        return self.pricing.get_account_prices(account_id, request, **kwargs)

    def stream_account_prices(
        self,
        account_id: str,
        request: om.PricingStreamRequest | None = None,
        **kwargs: Any,
    ) -> om.OandaResponse[None]:
        """Stream account prices."""
        return self.pricing.stream_account_prices(account_id, request, **kwargs)

    def get_account_candles(
        self,
        account_id: str,
        instrument: str,
        request: om.AccountCandlesRequest | None = None,
        **kwargs: Any,
    ) -> om.OandaResponse[om.CandlestickResponse]:
        """Fetch account-specific candles."""
        return self.pricing.get_account_candles(account_id, instrument, request, **kwargs)

    def get_instrument_candles(
        self,
        instrument: str,
        **kwargs: Any,
    ) -> om.OandaResponse[om.CandlestickResponse]:
        """Fetch public instrument candles."""
        return self.pricing.get_instrument_candles(instrument, **kwargs)

    def get_instrument_prices(
        self, instrument: str, **kwargs: Any
    ) -> om.OandaResponse[om.PricingResponse]:
        """Fetch account-independent instrument prices when supported by OANDA."""
        return self.pricing.get_instrument_prices(instrument, **kwargs)

    def list_trades(
        self,
        account_id: str,
        request: om.TradesRequest | None = None,
    ) -> om.OandaResponse[om.TradesResponse]:
        """List trades."""
        return self.trades.list_trades(account_id, request)

    def list_open_trades(self, account_id: str) -> om.OandaResponse[om.TradesResponse]:
        """List open trades."""
        return self.trades.list_open_trades(account_id)

    def get_trade(
        self, account_id: str, trade_specifier: str
    ) -> om.OandaResponse[om.TradeResponse]:
        """Get one trade."""
        return self.trades.get_trade(account_id, trade_specifier)

    def close_trade(
        self,
        account_id: str,
        trade_specifier: str,
        request: om.CloseTradeRequest | None = None,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.TradeTransactionResponse]:
        """Close one trade."""
        return self.trades.close_trade(account_id, trade_specifier, request, retry=retry, **kwargs)

    def set_trade_client_extensions(
        self,
        account_id: str,
        trade_specifier: str,
        request: om.SetTradeClientExtensionsRequest | None = None,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.TradeTransactionResponse]:
        """Set trade client extensions."""
        return self.trades.set_trade_client_extensions(
            account_id, trade_specifier, request, retry=retry, **kwargs
        )

    def set_trade_dependent_orders(
        self,
        account_id: str,
        trade_specifier: str,
        request: om.SetTradeDependentOrdersRequest | None = None,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.TradeTransactionResponse]:
        """Set trade dependent orders."""
        return self.trades.set_trade_dependent_orders(
            account_id, trade_specifier, request, retry=retry, **kwargs
        )

    def list_transactions(
        self,
        account_id: str,
        request: om.TransactionsRequest | None = None,
    ) -> om.OandaResponse[om.TransactionPagesResponse]:
        """List transaction pages."""
        return self.transactions.list_transactions(account_id, request)

    def get_transaction(
        self,
        account_id: str,
        transaction_id: str,
    ) -> om.OandaResponse[om.TransactionResponse]:
        """Get one transaction."""
        return self.transactions.get_transaction(account_id, transaction_id)

    def get_transaction_range(
        self,
        account_id: str,
        request: om.TransactionRangeRequest | None = None,
        **kwargs: Any,
    ) -> om.OandaResponse[om.TransactionsResponse]:
        """Get a transaction ID range."""
        return self.transactions.get_transaction_range(account_id, request, **kwargs)

    def get_transactions_since(
        self,
        account_id: str,
        request: om.TransactionsSinceRequest | None = None,
        **kwargs: Any,
    ) -> om.OandaResponse[om.TransactionsResponse]:
        """Get transactions since an ID."""
        return self.transactions.get_transactions_since(account_id, request, **kwargs)

    def stream_transactions(self, account_id: str) -> om.OandaResponse[None]:
        """Stream transactions."""
        return self.transactions.stream_transactions(account_id)


__all__ = ["OandaGateway", "OandaRetryPolicy"]
