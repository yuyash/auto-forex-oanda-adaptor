"""Low-level OANDA REST v20 API gateway."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, TypeVar, cast, overload
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener

from pydantic import BaseModel
from tenacity import (
    Retrying,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

import oanda.models as om
from oanda.config import (
    OandaEnvironment,
    OandaSettings,
)
from oanda.errors import (
    OandaConnectionError,
    OandaRetryableApiError,
    OandaTimeoutError,
    error_from_response,
)

_LOGGER = logging.getLogger(__name__)
_RETRYABLE_EXCEPTIONS = (
    OandaConnectionError,
    OandaTimeoutError,
    OandaRetryableApiError,
)
_SUCCESS = (200,)
_CREATED = (201,)
_ORDER_REJECTED = (400, 404)

TModel = TypeVar("TModel", bound=om.OandaModel)


@dataclass(frozen=True, slots=True)
class OandaRetryPolicy:
    """Retry policy for retryable OANDA transport and API failures."""

    attempts: int = 3
    initial_seconds: float = 0.25
    max_seconds: float = 4.0
    multiplier: float = 2.0

    def __post_init__(self) -> None:
        if self.attempts < 1:
            msg = "retry attempts must be greater than or equal to 1"
            raise ValueError(msg)
        if self.initial_seconds < 0:
            msg = "retry initial seconds must be greater than or equal to 0"
            raise ValueError(msg)
        if self.max_seconds < 0:
            msg = "retry max seconds must be greater than or equal to 0"
            raise ValueError(msg)
        if self.multiplier < 1:
            msg = "retry multiplier must be greater than or equal to 1"
            raise ValueError(msg)

    @classmethod
    def from_settings(cls, settings: OandaSettings) -> OandaRetryPolicy:
        """Create a retry policy from OANDA settings."""
        return cls(
            attempts=settings.retry_attempts,
            initial_seconds=settings.retry_initial_seconds,
            max_seconds=settings.retry_max_seconds,
            multiplier=settings.retry_multiplier,
        )

    def retrying(self) -> Retrying:
        """Return a tenacity retry controller."""
        return Retrying(
            retry=retry_if_exception_type(_RETRYABLE_EXCEPTIONS),
            stop=stop_after_attempt(self.attempts),
            wait=wait_exponential(
                multiplier=self.initial_seconds,
                max=self.max_seconds,
                exp_base=self.multiplier,
            ),
            before_sleep=before_sleep_log(_LOGGER, logging.WARNING),
            reraise=True,
        )


class OandaGateway:
    """Direct REST client for the OANDA REST v20 API."""

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
    ) -> None:
        self.access_token = access_token
        self.hostname = hostname
        self.stream_hostname = stream_hostname
        self.port = port
        self.ssl = ssl
        self.application = application
        self.poll_timeout = poll_timeout
        self.stream_timeout = stream_timeout
        self.retry_policy = retry_policy or OandaRetryPolicy()
        self.opener = opener or build_opener()

    @classmethod
    def from_settings(cls, settings: OandaSettings) -> OandaGateway:
        """Create a gateway from OANDA settings."""
        return cls.from_credentials(
            access_token=settings.access_token.get_secret_value(),
            environment=settings.environment,
            hostname=settings.hostname,
            stream_hostname=settings.stream_hostname,
            port=settings.port,
            ssl=settings.ssl,
            application=settings.application,
            stream_timeout=settings.stream_timeout,
            poll_timeout=settings.poll_timeout,
            retry_policy=OandaRetryPolicy.from_settings(settings),
        )

    @classmethod
    def from_credentials(
        cls,
        *,
        access_token: str,
        environment: OandaEnvironment = OandaEnvironment.PRACTICE,
        hostname: str | None = None,
        stream_hostname: str | None = None,
        port: int = 443,
        ssl: bool = True,
        application: str = "AutoForexV2",
        stream_chunk_size: int = 512,
        stream_timeout: int = 60,
        poll_timeout: int = 10,
        retry_policy: OandaRetryPolicy | None = None,
        retry_attempts: int = 3,
        retry_initial_seconds: float = 0.25,
        retry_max_seconds: float = 4.0,
        retry_multiplier: float = 2.0,
    ) -> OandaGateway:
        """Create a gateway directly from OANDA credentials."""
        _ = stream_chunk_size
        return cls(
            access_token=access_token,
            hostname=hostname or environment.default_hostname,
            stream_hostname=stream_hostname or environment.default_stream_hostname,
            port=port,
            ssl=ssl,
            application=application,
            stream_timeout=stream_timeout,
            poll_timeout=poll_timeout,
            retry_policy=retry_policy
            or OandaRetryPolicy(
                attempts=retry_attempts,
                initial_seconds=retry_initial_seconds,
                max_seconds=retry_max_seconds,
                multiplier=retry_multiplier,
            ),
        )

    def datetime_to_str(self, value: Any) -> str:
        """Format a datetime value for OANDA query parameters."""
        if isinstance(value, datetime):
            text = value.isoformat()
            return text.replace("+00:00", "Z")
        return str(value)

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
        return self._request(
            method,
            path,
            dict,
            query=query,
            body=body,
            retry=retry,
        )

    def list_accounts(self) -> om.OandaResponse[om.AccountsResponse]:
        """List accounts authorized for the token."""
        return self._request("GET", "/v3/accounts", om.AccountsResponse)

    def get_account(self, account_id: str) -> om.OandaResponse[om.AccountResponse]:
        """Get full account details."""
        return self._request("GET", f"/v3/accounts/{account_id}", om.AccountResponse)

    def get_account_summary(self, account_id: str) -> om.OandaResponse[om.AccountSummaryResponse]:
        """Get account summary."""
        return self._request("GET", f"/v3/accounts/{account_id}/summary", om.AccountSummaryResponse)

    def get_account_instruments(
        self,
        account_id: str,
        request: om.AccountInstrumentsRequest | Mapping[str, Any] | None = None,
    ) -> om.OandaResponse[om.AccountInstrumentsResponse]:
        """Get account tradable instruments."""
        return self._request(
            "GET",
            f"/v3/accounts/{account_id}/instruments",
            om.AccountInstrumentsResponse,
            query=request,
        )

    def configure_account(
        self,
        account_id: str,
        request: om.ConfigureAccountRequest | Mapping[str, Any] | None = None,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.ConfigureAccountResponse]:
        """Configure account alias or margin settings."""
        body = request if request is not None else kwargs
        return self._request(
            "PATCH",
            f"/v3/accounts/{account_id}/configuration",
            om.ConfigureAccountResponse,
            body=body,
            return_error_statuses=(400, 403),
            retry=retry,
        )

    def get_account_changes(
        self,
        account_id: str,
        request: om.AccountChangesRequest | Mapping[str, Any] | None = None,
    ) -> om.OandaResponse[om.AccountChangesResponse]:
        """Get account changes since a transaction ID."""
        return self._request(
            "GET",
            f"/v3/accounts/{account_id}/changes",
            om.AccountChangesResponse,
            query=request,
        )

    def create_order(
        self,
        account_id: str,
        request: om.CreateOrderRequest | Mapping[str, Any] | None = None,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.OrderTransactionResponse]:
        """Create an order."""
        body = request if request is not None else kwargs
        return self._request(
            "POST",
            f"/v3/accounts/{account_id}/orders",
            om.OrderTransactionResponse,
            body=body,
            success_statuses=_CREATED,
            return_error_statuses=_ORDER_REJECTED,
            retry=retry,
        )

    def list_orders(
        self,
        account_id: str,
        request: om.OrdersRequest | Mapping[str, Any] | None = None,
    ) -> om.OandaResponse[om.OrdersResponse]:
        """List orders."""
        return self._request(
            "GET", f"/v3/accounts/{account_id}/orders", om.OrdersResponse, query=request
        )

    def list_pending_orders(self, account_id: str) -> om.OandaResponse[om.OrdersResponse]:
        """List pending orders."""
        return self._request("GET", f"/v3/accounts/{account_id}/pendingOrders", om.OrdersResponse)

    def get_order(
        self, account_id: str, order_specifier: str
    ) -> om.OandaResponse[om.OrderResponse]:
        """Get one order."""
        return self._request(
            "GET",
            f"/v3/accounts/{account_id}/orders/{order_specifier}",
            om.OrderResponse,
        )

    def replace_order(
        self,
        account_id: str,
        order_specifier: str,
        request: om.ReplaceOrderRequest | Mapping[str, Any] | None = None,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.OrderTransactionResponse]:
        """Replace one order."""
        body = request if request is not None else kwargs
        return self._request(
            "PUT",
            f"/v3/accounts/{account_id}/orders/{order_specifier}",
            om.OrderTransactionResponse,
            body=body,
            success_statuses=_CREATED,
            return_error_statuses=_ORDER_REJECTED,
            retry=retry,
        )

    def cancel_order(
        self,
        account_id: str,
        order_specifier: str,
        *,
        retry: bool = False,
    ) -> om.OandaResponse[om.OrderTransactionResponse]:
        """Cancel one order."""
        return self._request(
            "PUT",
            f"/v3/accounts/{account_id}/orders/{order_specifier}/cancel",
            om.OrderTransactionResponse,
            return_error_statuses=(404,),
            retry=retry,
        )

    def set_order_client_extensions(
        self,
        account_id: str,
        order_specifier: str,
        request: om.SetOrderClientExtensionsRequest | Mapping[str, Any] | None = None,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.OrderTransactionResponse]:
        """Set order client extensions."""
        body = request if request is not None else kwargs
        return self._request(
            "PUT",
            f"/v3/accounts/{account_id}/orders/{order_specifier}/clientExtensions",
            om.OrderTransactionResponse,
            body=body,
            return_error_statuses=(400, 404),
            retry=retry,
        )

    def create_market_order(
        self,
        account_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.OrderTransactionResponse]:
        """Create a market order."""
        return self.create_order(account_id, {"order": {**kwargs, "type": "MARKET"}}, retry=retry)

    def create_limit_order(
        self,
        account_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.OrderTransactionResponse]:
        """Create a limit order."""
        return self.create_order(account_id, {"order": {**kwargs, "type": "LIMIT"}}, retry=retry)

    def replace_limit_order(
        self,
        account_id: str,
        order_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.OrderTransactionResponse]:
        """Replace a limit order."""
        return self.replace_order(
            account_id, order_id, {"order": {**kwargs, "type": "LIMIT"}}, retry=retry
        )

    def create_stop_order(
        self,
        account_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.OrderTransactionResponse]:
        """Create a stop order."""
        return self.create_order(account_id, {"order": {**kwargs, "type": "STOP"}}, retry=retry)

    def replace_stop_order(
        self,
        account_id: str,
        order_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.OrderTransactionResponse]:
        """Replace a stop order."""
        return self.replace_order(
            account_id, order_id, {"order": {**kwargs, "type": "STOP"}}, retry=retry
        )

    def create_market_if_touched_order(
        self,
        account_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.OrderTransactionResponse]:
        """Create a market-if-touched order."""
        return self.create_order(
            account_id,
            {"order": {**kwargs, "type": "MARKET_IF_TOUCHED"}},
            retry=retry,
        )

    def replace_market_if_touched_order(
        self,
        account_id: str,
        order_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.OrderTransactionResponse]:
        """Replace a market-if-touched order."""
        return self.replace_order(
            account_id,
            order_id,
            {"order": {**kwargs, "type": "MARKET_IF_TOUCHED"}},
            retry=retry,
        )

    def create_take_profit_order(
        self,
        account_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.OrderTransactionResponse]:
        """Create a take-profit order."""
        return self.create_order(
            account_id, {"order": {**kwargs, "type": "TAKE_PROFIT"}}, retry=retry
        )

    def replace_take_profit_order(
        self,
        account_id: str,
        order_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.OrderTransactionResponse]:
        """Replace a take-profit order."""
        return self.replace_order(
            account_id,
            order_id,
            {"order": {**kwargs, "type": "TAKE_PROFIT"}},
            retry=retry,
        )

    def create_stop_loss_order(
        self,
        account_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.OrderTransactionResponse]:
        """Create a stop-loss order."""
        return self.create_order(
            account_id, {"order": {**kwargs, "type": "STOP_LOSS"}}, retry=retry
        )

    def replace_stop_loss_order(
        self,
        account_id: str,
        order_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.OrderTransactionResponse]:
        """Replace a stop-loss order."""
        return self.replace_order(
            account_id,
            order_id,
            {"order": {**kwargs, "type": "STOP_LOSS"}},
            retry=retry,
        )

    def create_trailing_stop_loss_order(
        self,
        account_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.OrderTransactionResponse]:
        """Create a trailing stop-loss order."""
        return self.create_order(
            account_id,
            {"order": {**kwargs, "type": "TRAILING_STOP_LOSS"}},
            retry=retry,
        )

    def replace_trailing_stop_loss_order(
        self,
        account_id: str,
        order_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.OrderTransactionResponse]:
        """Replace a trailing stop-loss order."""
        return self.replace_order(
            account_id,
            order_id,
            {"order": {**kwargs, "type": "TRAILING_STOP_LOSS"}},
            retry=retry,
        )

    def list_positions(self, account_id: str) -> om.OandaResponse[om.PositionsResponse]:
        """List positions."""
        return self._request("GET", f"/v3/accounts/{account_id}/positions", om.PositionsResponse)

    def list_open_positions(self, account_id: str) -> om.OandaResponse[om.PositionsResponse]:
        """List open positions."""
        return self._request(
            "GET", f"/v3/accounts/{account_id}/openPositions", om.PositionsResponse
        )

    def get_position(
        self, account_id: str, instrument: str
    ) -> om.OandaResponse[om.PositionResponse]:
        """Get one position."""
        return self._request(
            "GET",
            f"/v3/accounts/{account_id}/positions/{instrument}",
            om.PositionResponse,
        )

    def close_position(
        self,
        account_id: str,
        instrument: str,
        request: om.ClosePositionRequest | Mapping[str, Any] | None = None,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.PositionCloseResponse]:
        """Close one position."""
        body = request if request is not None else kwargs
        return self._request(
            "PUT",
            f"/v3/accounts/{account_id}/positions/{instrument}/close",
            om.PositionCloseResponse,
            body=body,
            return_error_statuses=_ORDER_REJECTED,
            retry=retry,
        )

    def get_account_prices(
        self,
        account_id: str,
        request: om.PricingRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> om.OandaResponse[om.PricingResponse]:
        """Get account prices."""
        query = request if request is not None else kwargs
        return self._request(
            "GET", f"/v3/accounts/{account_id}/pricing", om.PricingResponse, query=query
        )

    def stream_account_prices(
        self,
        account_id: str,
        request: om.PricingStreamRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> om.OandaResponse[None]:
        """Stream account prices."""
        query = request if request is not None else kwargs
        return self._stream(
            "GET",
            f"/v3/accounts/{account_id}/pricing/stream",
            query=query,
            stream_kind="pricing",
        )

    def get_account_candles(
        self,
        account_id: str,
        instrument: str,
        request: om.AccountCandlesRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> om.OandaResponse[om.CandlestickResponse]:
        """Fetch account-specific candles."""
        query = request if request is not None else kwargs
        return self._request(
            "GET",
            f"/v3/accounts/{account_id}/instruments/{instrument}/candles",
            om.CandlestickResponse,
            query=query,
        )

    def get_instrument_candles(
        self,
        instrument: str,
        **kwargs: Any,
    ) -> om.OandaResponse[om.CandlestickResponse]:
        """Fetch public instrument candles."""
        return self._request(
            "GET",
            f"/v3/instruments/{instrument}/candles",
            om.CandlestickResponse,
            query=kwargs,
        )

    def get_instrument_prices(
        self, instrument: str, **kwargs: Any
    ) -> om.OandaResponse[om.PricingResponse]:
        """Fetch account-independent instrument prices when supported by OANDA."""
        return self._request(
            "GET",
            f"/v3/instruments/{instrument}/prices",
            om.PricingResponse,
            query=kwargs,
        )

    def list_trades(
        self,
        account_id: str,
        request: om.TradesRequest | Mapping[str, Any] | None = None,
    ) -> om.OandaResponse[om.TradesResponse]:
        """List trades."""
        return self._request(
            "GET", f"/v3/accounts/{account_id}/trades", om.TradesResponse, query=request
        )

    def list_open_trades(self, account_id: str) -> om.OandaResponse[om.TradesResponse]:
        """List open trades."""
        return self._request("GET", f"/v3/accounts/{account_id}/openTrades", om.TradesResponse)

    def get_trade(
        self, account_id: str, trade_specifier: str
    ) -> om.OandaResponse[om.TradeResponse]:
        """Get one trade."""
        return self._request(
            "GET",
            f"/v3/accounts/{account_id}/trades/{trade_specifier}",
            om.TradeResponse,
        )

    def close_trade(
        self,
        account_id: str,
        trade_specifier: str,
        request: om.CloseTradeRequest | Mapping[str, Any] | None = None,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.TradeTransactionResponse]:
        """Close one trade."""
        body = request if request is not None else kwargs
        return self._request(
            "PUT",
            f"/v3/accounts/{account_id}/trades/{trade_specifier}/close",
            om.TradeTransactionResponse,
            body=body,
            return_error_statuses=_ORDER_REJECTED,
            retry=retry,
        )

    def set_trade_client_extensions(
        self,
        account_id: str,
        trade_specifier: str,
        request: om.SetTradeClientExtensionsRequest | Mapping[str, Any] | None = None,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.TradeTransactionResponse]:
        """Set trade client extensions."""
        body = request if request is not None else kwargs
        return self._request(
            "PUT",
            f"/v3/accounts/{account_id}/trades/{trade_specifier}/clientExtensions",
            om.TradeTransactionResponse,
            body=body,
            return_error_statuses=(400, 404),
            retry=retry,
        )

    def set_trade_dependent_orders(
        self,
        account_id: str,
        trade_specifier: str,
        request: om.SetTradeDependentOrdersRequest | Mapping[str, Any] | None = None,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> om.OandaResponse[om.TradeTransactionResponse]:
        """Set trade dependent orders."""
        body = request if request is not None else kwargs
        return self._request(
            "PUT",
            f"/v3/accounts/{account_id}/trades/{trade_specifier}/orders",
            om.TradeTransactionResponse,
            body=body,
            return_error_statuses=_ORDER_REJECTED,
            retry=retry,
        )

    def list_transactions(
        self,
        account_id: str,
        request: om.TransactionsRequest | Mapping[str, Any] | None = None,
    ) -> om.OandaResponse[om.TransactionPagesResponse]:
        """List transaction pages."""
        return self._request(
            "GET",
            f"/v3/accounts/{account_id}/transactions",
            om.TransactionPagesResponse,
            query=request,
        )

    def get_transaction(
        self,
        account_id: str,
        transaction_id: str,
    ) -> om.OandaResponse[om.TransactionResponse]:
        """Get one transaction."""
        return self._request(
            "GET",
            f"/v3/accounts/{account_id}/transactions/{transaction_id}",
            om.TransactionResponse,
        )

    def get_transaction_range(
        self,
        account_id: str,
        request: om.TransactionRangeRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> om.OandaResponse[om.TransactionsResponse]:
        """Get a transaction ID range."""
        query = (
            request if request is not None else om.TransactionRangeRequest.model_validate(kwargs)
        )
        return self._request(
            "GET",
            f"/v3/accounts/{account_id}/transactions/idrange",
            om.TransactionsResponse,
            query=query,
        )

    def get_transactions_since(
        self,
        account_id: str,
        request: om.TransactionsSinceRequest | Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> om.OandaResponse[om.TransactionsResponse]:
        """Get transactions since an ID."""
        query = request if request is not None else kwargs
        return self._request(
            "GET",
            f"/v3/accounts/{account_id}/transactions/sinceid",
            om.TransactionsResponse,
            query=query,
        )

    def stream_transactions(self, account_id: str) -> om.OandaResponse[None]:
        """Stream transactions."""
        return self._stream(
            "GET",
            f"/v3/accounts/{account_id}/transactions/stream",
            stream_kind="transactions",
        )

    @overload
    def _request(
        self,
        method: str,
        path: str,
        response_model: type[TModel],
        *,
        query: Any = None,
        body: Any = None,
        success_statuses: Iterable[int] = _SUCCESS,
        return_error_statuses: Iterable[int] = (),
        retry: bool = True,
    ) -> om.OandaResponse[TModel]: ...

    @overload
    def _request(
        self,
        method: str,
        path: str,
        response_model: type[dict[str, Any]],
        *,
        query: Any = None,
        body: Any = None,
        success_statuses: Iterable[int] = _SUCCESS,
        return_error_statuses: Iterable[int] = (),
        retry: bool = True,
    ) -> om.OandaResponse[dict[str, Any]]: ...

    def _request(
        self,
        method: str,
        path: str,
        response_model: type[TModel] | type[dict[str, Any]],
        *,
        query: Any = None,
        body: Any = None,
        success_statuses: Iterable[int] = _SUCCESS,
        return_error_statuses: Iterable[int] = (),
        retry: bool = True,
    ) -> om.OandaResponse[TModel] | om.OandaResponse[dict[str, Any]]:
        success = frozenset(success_statuses)
        allowed_errors = frozenset(return_error_statuses)

        def execute() -> om.OandaResponse[TModel] | om.OandaResponse[dict[str, Any]]:
            raw = self._send(method, path, query=query, body=body)
            if raw.status not in success and raw.status not in allowed_errors:
                raise error_from_response(om.OandaResponse(raw=raw, body=raw.body))
            if response_model is dict:
                return om.OandaResponse(raw=raw, body=raw.body)
            model_cls = cast(type[TModel], response_model)
            return om.OandaResponse(raw=raw, body=model_cls.model_validate(raw.body))

        if retry:
            return self._retry(execute)
        return execute()

    def _stream(
        self,
        method: str,
        path: str,
        *,
        query: Any = None,
        stream_kind: str,
    ) -> om.OandaResponse[None]:
        raw = self._open_stream(method, path, query=query, stream_kind=stream_kind)
        if raw.status != 200:
            raise error_from_response(om.OandaResponse(raw=raw, body={}))
        return om.OandaResponse(raw=raw, body=None)

    def _retry(self, operation: Callable[[], Any]) -> Any:
        if self.retry_policy.attempts <= 1:
            return operation()
        return self.retry_policy.retrying()(operation)

    def _send(
        self, method: str, path: str, *, query: Any = None, body: Any = None
    ) -> om.OandaHttpResponse:
        url = self._url(path, query=query)
        request = self._build_request(method, url, body=body)
        try:
            response = self.opener.open(request, timeout=self.poll_timeout)
            return self._read_response(response, url)
        except HTTPError as exc:
            return self._read_response(exc, url)
        except TimeoutError as exc:
            raise OandaTimeoutError(str(exc), url=url, timeout_type="read") from exc
        except URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise OandaTimeoutError(str(exc.reason), url=url, timeout_type="connect") from exc
            raise OandaConnectionError(str(exc.reason), url=url) from exc

    def _open_stream(
        self,
        method: str,
        path: str,
        *,
        query: Any = None,
        stream_kind: str,
    ) -> om.OandaStreamResponse:
        url = self._url(path, query=query, stream=True)
        request = self._build_request(method, url, body=None)
        try:
            response = self.opener.open(request, timeout=self.stream_timeout)
        except HTTPError as exc:
            body = exc.read()
            raw = om.OandaHttpResponse(
                status=int(exc.code),
                reason=str(exc.reason),
                headers=dict(exc.headers.items()),
                body=self._json_body(body),
                raw_body=body,
                url=url,
                content_type=exc.headers.get("Content-Type"),
            )
            raise error_from_response(om.OandaResponse(raw=raw, body=raw.body)) from exc
        except TimeoutError as exc:
            raise OandaTimeoutError(str(exc), url=url, timeout_type="stream") from exc
        except URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise OandaTimeoutError(str(exc.reason), url=url, timeout_type="connect") from exc
            raise OandaConnectionError(str(exc.reason), url=url) from exc

        return om.OandaStreamResponse(
            status=int(getattr(response, "status", getattr(response, "code", 0))),
            reason=str(getattr(response, "reason", "") or ""),
            headers=dict(response.headers.items()),
            stream=response,
            url=url,
            content_type=response.headers.get("Content-Type"),
            stream_kind=stream_kind,
        )

    def _build_request(self, method: str, url: str, *, body: Any) -> Request:
        payload = None
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.access_token}",
            "User-Agent": self.application,
        }
        if body is not None:
            payload = json.dumps(
                self._jsonable(self._model_dump(body)),
                separators=(",", ":"),
            ).encode()
            headers["Content-Type"] = "application/json"
        return Request(url, data=payload, headers=headers, method=method)

    def _url(self, path: str, *, query: Any = None, stream: bool = False) -> str:
        scheme = "https" if self.ssl else "http"
        hostname = self.stream_hostname if stream else self.hostname
        default_port = 443 if self.ssl else 80
        netloc = hostname if self.port == default_port else f"{hostname}:{self.port}"
        query_values = self._query_dump(query)
        suffix = f"?{urlencode(query_values)}" if query_values else ""
        return f"{scheme}://{netloc}{path}{suffix}"

    @staticmethod
    def _read_response(response: Any, url: str) -> om.OandaHttpResponse:
        body = response.read()
        return om.OandaHttpResponse(
            status=int(getattr(response, "status", getattr(response, "code", 0))),
            reason=str(getattr(response, "reason", "") or ""),
            headers=dict(response.headers.items()),
            body=OandaGateway._json_body(body),
            raw_body=body,
            url=url,
            content_type=response.headers.get("Content-Type"),
        )

    @staticmethod
    def _json_body(body: bytes) -> Any:
        if not body:
            return {}
        return json.loads(body.decode("utf-8"))

    @classmethod
    def _model_dump(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, BaseModel):
            return value.model_dump(by_alias=True, exclude_none=True, mode="json")
        if isinstance(value, Mapping):
            return {key: cls._model_dump(item) for key, item in value.items() if item is not None}
        if isinstance(value, tuple | list):
            return [cls._model_dump(item) for item in value]
        return value

    @classmethod
    def _query_dump(cls, value: Any) -> dict[str, str]:
        data = cls._model_dump(value)
        if not data:
            return {}
        if not isinstance(data, Mapping):
            msg = "query parameters must be a mapping or OandaModel"
            raise TypeError(msg)
        return {
            str(key): cls._query_value(item)
            for key, item in data.items()
            if item is not None and item != ()
        }

    @classmethod
    def _query_value(cls, value: Any) -> str:
        if isinstance(value, tuple | list):
            return ",".join(cls._query_value(item) for item in value)
        if isinstance(value, bool):
            return str(value).lower()
        if isinstance(value, Enum):
            return str(value.value)
        if isinstance(value, datetime):
            return value.isoformat().replace("+00:00", "Z")
        if isinstance(value, Decimal):
            return str(value)
        return str(value)

    @classmethod
    def _jsonable(cls, value: Any) -> Any:
        if isinstance(value, Mapping):
            return {str(key): cls._jsonable(item) for key, item in value.items()}
        if isinstance(value, tuple | list):
            return [cls._jsonable(item) for item in value]
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, datetime):
            return value.isoformat().replace("+00:00", "Z")
        if isinstance(value, Decimal):
            return str(value)
        return value
