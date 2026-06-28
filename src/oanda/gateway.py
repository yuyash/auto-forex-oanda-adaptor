"""Low-level OANDA v20 API gateway."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

import ujson as json
import v20
from tenacity import (
    Retrying,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from v20.errors import (
    ResponseNoField,
    ResponseUnexpectedStatus,
    V20ConnectionError,
    V20Timeout,
)
from v20.request import Request

from oanda.config import (
    OandaEnvironment,
    OandaSettings,
    default_hostname_for_environment,
)
from oanda.errors import (
    OandaAdapterError,
    OandaConnectionError,
    OandaRetryableApiError,
    OandaTimeoutError,
    error_from_response,
    response_status_code,
)

V20Response = Any
_LOGGER = logging.getLogger(__name__)
_RETRYABLE_EXCEPTIONS = (
    OandaConnectionError,
    OandaTimeoutError,
    OandaRetryableApiError,
)
_SUCCESS = (200,)
_CREATED = (201,)
_ORDER_REJECTED = (400, 404)


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
    """Wrapper around the OANDA v20 generated API surface."""

    def __init__(
        self,
        context: Any,
        *,
        retry_policy: OandaRetryPolicy | None = None,
    ) -> None:
        self.context = context
        self.retry_policy = retry_policy or OandaRetryPolicy()

    @classmethod
    def from_settings(cls, settings: OandaSettings) -> OandaGateway:
        """Create a gateway from OANDA settings."""
        return cls.from_credentials(
            access_token=settings.access_token.get_secret_value(),
            environment=settings.environment,
            hostname=settings.hostname,
            port=settings.port,
            ssl=settings.ssl,
            application=settings.application,
            stream_chunk_size=settings.stream_chunk_size,
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
        context = v20.Context(
            hostname or default_hostname_for_environment(environment),
            port=port,
            ssl=ssl,
            application=application,
            token=access_token,
            decimal_number_as_float=False,
            stream_chunk_size=stream_chunk_size,
            stream_timeout=stream_timeout,
            poll_timeout=poll_timeout,
        )
        return cls(
            context,
            retry_policy=retry_policy
            or OandaRetryPolicy(
                attempts=retry_attempts,
                initial_seconds=retry_initial_seconds,
                max_seconds=retry_max_seconds,
                multiplier=retry_multiplier,
            ),
        )

    def request(self, request: Request, *, retry: bool = False) -> V20Response:
        """Execute a raw v20 request.

        Raw requests may be non-idempotent, so status-code based retry is not
        applied here. Transport failures can still be retried when requested.
        """

        def operation() -> V20Response:
            return self.context.request(request)

        if retry:
            return self._retry(lambda: self._transport_call(operation))
        return self._transport_call(operation)

    def datetime_to_str(self, value: Any) -> str:
        """Format a datetime value using the underlying v20 context."""
        return str(self.context.datetime_to_str(value))

    def list_accounts(self, **kwargs: Any) -> V20Response:
        """List accounts authorized for the token."""
        return self._spec_call("account", "list", **kwargs)

    def get_account(self, account_id: str, **kwargs: Any) -> V20Response:
        """Get full account details."""
        return self._spec_call("account", "get", account_id, **kwargs)

    def get_account_summary(self, account_id: str, **kwargs: Any) -> V20Response:
        """Get account summary."""
        return self._spec_call("account", "summary", account_id, **kwargs)

    def get_account_instruments(self, account_id: str, **kwargs: Any) -> V20Response:
        """Get account tradable instruments."""
        return self._spec_call("account", "instruments", account_id, **kwargs)

    def configure_account(
        self,
        account_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> V20Response:
        """Configure account alias or margin settings."""
        return self._spec_call("account", "configure", account_id, retry=retry, **kwargs)

    def get_account_changes(self, account_id: str, **kwargs: Any) -> V20Response:
        """Get account changes since a transaction ID."""
        return self._spec_call("account", "changes", account_id, **kwargs)

    def get_instrument_candles(self, instrument: str, **kwargs: Any) -> V20Response:
        """Fetch instrument candles."""
        return self._spec_call("instrument", "candles", instrument, **kwargs)

    def get_instrument_price(self, instrument: str, **kwargs: Any) -> V20Response:
        """Fetch an instrument price."""
        return self._spec_call("instrument", "price", instrument, **kwargs)

    def get_instrument_prices(self, instrument: str, **kwargs: Any) -> V20Response:
        """Fetch an instrument price range."""
        return self._spec_call("instrument", "prices", instrument, **kwargs)

    def get_instrument_order_book(self, instrument: str, **kwargs: Any) -> V20Response:
        """Fetch an instrument order book."""
        return self._spec_call("instrument", "order_book", instrument, **kwargs)

    def get_instrument_position_book(self, instrument: str, **kwargs: Any) -> V20Response:
        """Fetch an instrument position book."""
        return self._spec_call("instrument", "position_book", instrument, **kwargs)

    def create_order(
        self,
        account_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> V20Response:
        """Create an order."""
        return self._spec_call(
            "order",
            "create",
            account_id,
            success_statuses=_CREATED,
            return_error_statuses=_ORDER_REJECTED,
            retry=retry,
            **kwargs,
        )

    def list_orders(self, account_id: str, **kwargs: Any) -> V20Response:
        """List orders."""
        return self._spec_call("order", "list", account_id, **kwargs)

    def list_pending_orders(self, account_id: str, **kwargs: Any) -> V20Response:
        """List pending orders."""
        return self._spec_call("order", "list_pending", account_id, **kwargs)

    def get_order(self, account_id: str, order_specifier: str, **kwargs: Any) -> V20Response:
        """Get one order."""
        return self._spec_call("order", "get", account_id, order_specifier, **kwargs)

    def replace_order(
        self,
        account_id: str,
        order_specifier: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> V20Response:
        """Replace one order."""
        return self._spec_call(
            "order",
            "replace",
            account_id,
            order_specifier,
            success_statuses=_CREATED,
            return_error_statuses=_ORDER_REJECTED,
            retry=retry,
            **kwargs,
        )

    def cancel_order(
        self,
        account_id: str,
        order_specifier: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> V20Response:
        """Cancel one order."""
        return self._spec_call(
            "order",
            "cancel",
            account_id,
            order_specifier,
            retry=retry,
            **kwargs,
        )

    def set_order_client_extensions(
        self,
        account_id: str,
        order_specifier: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> V20Response:
        """Set order client extensions."""
        return self._spec_call(
            "order",
            "set_client_extensions",
            account_id,
            order_specifier,
            retry=retry,
            **kwargs,
        )

    def create_market_order(
        self,
        account_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> V20Response:
        """Create a market order."""
        return self._spec_call(
            "order",
            "market",
            account_id,
            success_statuses=_CREATED,
            return_error_statuses=_ORDER_REJECTED,
            retry=retry,
            **kwargs,
        )

    def create_limit_order(
        self,
        account_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> V20Response:
        """Create a limit order."""
        return self._spec_call(
            "order",
            "limit",
            account_id,
            success_statuses=_CREATED,
            return_error_statuses=_ORDER_REJECTED,
            retry=retry,
            **kwargs,
        )

    def replace_limit_order(
        self,
        account_id: str,
        order_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> V20Response:
        """Replace a limit order."""
        return self._spec_call(
            "order",
            "limit_replace",
            account_id,
            order_id,
            success_statuses=_CREATED,
            return_error_statuses=_ORDER_REJECTED,
            retry=retry,
            **kwargs,
        )

    def create_stop_order(
        self,
        account_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> V20Response:
        """Create a stop order."""
        return self._spec_call(
            "order",
            "stop",
            account_id,
            success_statuses=_CREATED,
            return_error_statuses=_ORDER_REJECTED,
            retry=retry,
            **kwargs,
        )

    def replace_stop_order(
        self,
        account_id: str,
        order_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> V20Response:
        """Replace a stop order."""
        return self._spec_call(
            "order",
            "stop_replace",
            account_id,
            order_id,
            success_statuses=_CREATED,
            return_error_statuses=_ORDER_REJECTED,
            retry=retry,
            **kwargs,
        )

    def create_market_if_touched_order(
        self,
        account_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> V20Response:
        """Create a market-if-touched order."""
        return self._spec_call(
            "order",
            "market_if_touched",
            account_id,
            success_statuses=_CREATED,
            return_error_statuses=_ORDER_REJECTED,
            retry=retry,
            **kwargs,
        )

    def replace_market_if_touched_order(
        self,
        account_id: str,
        order_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> V20Response:
        """Replace a market-if-touched order."""
        return self._spec_call(
            "order",
            "market_if_touched_replace",
            account_id,
            order_id,
            success_statuses=_CREATED,
            return_error_statuses=_ORDER_REJECTED,
            retry=retry,
            **kwargs,
        )

    def create_take_profit_order(
        self,
        account_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> V20Response:
        """Create a take-profit order."""
        return self._spec_call(
            "order",
            "take_profit",
            account_id,
            success_statuses=_CREATED,
            return_error_statuses=_ORDER_REJECTED,
            retry=retry,
            **kwargs,
        )

    def replace_take_profit_order(
        self,
        account_id: str,
        order_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> V20Response:
        """Replace a take-profit order."""
        return self._spec_call(
            "order",
            "take_profit_replace",
            account_id,
            order_id,
            success_statuses=_CREATED,
            return_error_statuses=_ORDER_REJECTED,
            retry=retry,
            **kwargs,
        )

    def create_stop_loss_order(
        self,
        account_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> V20Response:
        """Create a stop-loss order."""
        return self._spec_call(
            "order",
            "stop_loss",
            account_id,
            success_statuses=_CREATED,
            return_error_statuses=_ORDER_REJECTED,
            retry=retry,
            **kwargs,
        )

    def replace_stop_loss_order(
        self,
        account_id: str,
        order_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> V20Response:
        """Replace a stop-loss order."""
        return self._spec_call(
            "order",
            "stop_loss_replace",
            account_id,
            order_id,
            success_statuses=_CREATED,
            return_error_statuses=_ORDER_REJECTED,
            retry=retry,
            **kwargs,
        )

    def create_trailing_stop_loss_order(
        self,
        account_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> V20Response:
        """Create a trailing stop-loss order."""
        return self._spec_call(
            "order",
            "trailing_stop_loss",
            account_id,
            success_statuses=_CREATED,
            return_error_statuses=_ORDER_REJECTED,
            retry=retry,
            **kwargs,
        )

    def replace_trailing_stop_loss_order(
        self,
        account_id: str,
        order_id: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> V20Response:
        """Replace a trailing stop-loss order."""
        return self._spec_call(
            "order",
            "trailing_stop_loss_replace",
            account_id,
            order_id,
            success_statuses=_CREATED,
            return_error_statuses=_ORDER_REJECTED,
            retry=retry,
            **kwargs,
        )

    def list_positions(self, account_id: str, **kwargs: Any) -> V20Response:
        """List positions."""
        return self._spec_call("position", "list", account_id, **kwargs)

    def list_open_positions(self, account_id: str, **kwargs: Any) -> V20Response:
        """List open positions."""
        return self._spec_call("position", "list_open", account_id, **kwargs)

    def get_position(self, account_id: str, instrument: str, **kwargs: Any) -> V20Response:
        """Get one position."""
        return self._spec_call("position", "get", account_id, instrument, **kwargs)

    def close_position(
        self,
        account_id: str,
        instrument: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> V20Response:
        """Close one position."""
        return self._spec_call(
            "position",
            "close",
            account_id,
            instrument,
            return_error_statuses=_ORDER_REJECTED,
            retry=retry,
            **kwargs,
        )

    def get_base_prices(self, **kwargs: Any) -> V20Response:
        """Get account-independent prices."""
        return self._spec_call("pricing", "base_prices", **kwargs)

    def get_price_range(self, instrument: str, **kwargs: Any) -> V20Response:
        """Get account-independent price range."""
        return self._spec_call("pricing", "get_price_range", instrument, **kwargs)

    def get_account_prices(self, account_id: str, **kwargs: Any) -> V20Response:
        """Get account prices."""
        return self._spec_call("pricing", "get", account_id, **kwargs)

    def stream_account_prices(self, account_id: str, **kwargs: Any) -> V20Response:
        """Stream account prices."""
        return self._spec_call("pricing", "stream", account_id, retry=False, **kwargs)

    def get_account_candles(
        self,
        account_id: str,
        instrument: str,
        **kwargs: Any,
    ) -> V20Response:
        """Fetch account-specific candles.

        The generated v20 binding for this endpoint does not expose accountID
        as a function argument, so this method creates the request explicitly.
        """
        request = Request("GET", "/v3/accounts/{accountID}/instruments/{instrument}/candles")
        request.set_path_param("accountID", account_id)
        request.set_path_param("instrument", instrument)
        for target, source in {
            "price": "price",
            "granularity": "granularity",
            "count": "count",
            "from": "fromTime",
            "to": "toTime",
            "smooth": "smooth",
            "includeFirst": "includeFirst",
            "dailyAlignment": "dailyAlignment",
            "alignmentTimezone": "alignmentTimezone",
            "weeklyAlignment": "weeklyAlignment",
            "units": "units",
        }.items():
            request.set_param(target, kwargs.get(source))
        response = self._call(lambda: self.context.request(request))
        if response.content_type is None:
            return response
        if not response.content_type.startswith("application/json"):
            return response

        jbody = json.loads(response.raw_body)
        parsed_body: dict[str, Any] = {}
        if str(response.status) == "200":
            if jbody.get("candles") is not None:
                parsed_body["candles"] = [
                    self.context.instrument.Candlestick.from_dict(item, self.context)
                    for item in jbody.get("candles")
                ]
            if jbody.get("instrument") is not None:
                parsed_body["instrument"] = jbody.get("instrument")
            if jbody.get("granularity") is not None:
                parsed_body["granularity"] = jbody.get("granularity")
        else:
            parsed_body = jbody
        response.body = parsed_body
        return response

    def list_trades(self, account_id: str, **kwargs: Any) -> V20Response:
        """List trades."""
        return self._spec_call("trade", "list", account_id, **kwargs)

    def list_open_trades(self, account_id: str, **kwargs: Any) -> V20Response:
        """List open trades."""
        return self._spec_call("trade", "list_open", account_id, **kwargs)

    def get_trade(self, account_id: str, trade_specifier: str, **kwargs: Any) -> V20Response:
        """Get one trade."""
        return self._spec_call("trade", "get", account_id, trade_specifier, **kwargs)

    def close_trade(
        self,
        account_id: str,
        trade_specifier: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> V20Response:
        """Close one trade."""
        return self._spec_call(
            "trade",
            "close",
            account_id,
            trade_specifier,
            return_error_statuses=_ORDER_REJECTED,
            retry=retry,
            **kwargs,
        )

    def set_trade_client_extensions(
        self,
        account_id: str,
        trade_specifier: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> V20Response:
        """Set trade client extensions."""
        return self._spec_call(
            "trade",
            "set_client_extensions",
            account_id,
            trade_specifier,
            retry=retry,
            **kwargs,
        )

    def set_trade_dependent_orders(
        self,
        account_id: str,
        trade_specifier: str,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> V20Response:
        """Set trade dependent orders."""
        return self._spec_call(
            "trade",
            "set_dependent_orders",
            account_id,
            trade_specifier,
            return_error_statuses=_ORDER_REJECTED,
            retry=retry,
            **kwargs,
        )

    def list_transactions(self, account_id: str, **kwargs: Any) -> V20Response:
        """List transactions."""
        return self._spec_call("transaction", "list", account_id, **kwargs)

    def get_transaction(self, account_id: str, transaction_id: str, **kwargs: Any) -> V20Response:
        """Get one transaction."""
        return self._spec_call("transaction", "get", account_id, transaction_id, **kwargs)

    def get_transaction_range(self, account_id: str, **kwargs: Any) -> V20Response:
        """Get a transaction ID range."""
        return self._spec_call("transaction", "range", account_id, **kwargs)

    def get_transactions_since(self, account_id: str, **kwargs: Any) -> V20Response:
        """Get transactions since an ID."""
        return self._spec_call("transaction", "since", account_id, **kwargs)

    def stream_transactions(self, account_id: str, **kwargs: Any) -> V20Response:
        """Stream transactions."""
        return self._spec_call("transaction", "stream", account_id, retry=False, **kwargs)

    def _spec_call(
        self,
        spec_name: str,
        method_name: str,
        *args: Any,
        success_statuses: Iterable[int] = _SUCCESS,
        return_error_statuses: Iterable[int] = (),
        retry: bool = True,
        **kwargs: Any,
    ) -> V20Response:
        spec = getattr(self.context, spec_name)
        method = getattr(spec, method_name)
        return self._call(
            lambda: method(*args, **kwargs),
            success_statuses=success_statuses,
            return_error_statuses=return_error_statuses,
            retry=retry,
        )

    def _call(
        self,
        operation: Callable[[], V20Response],
        *,
        success_statuses: Iterable[int] = _SUCCESS,
        return_error_statuses: Iterable[int] = (),
        retry: bool = True,
    ) -> V20Response:
        success = frozenset(success_statuses)
        allowed_errors = frozenset(return_error_statuses)

        def execute() -> V20Response:
            response = self._transport_call(operation)
            status = response_status_code(response)
            if status in success or status in allowed_errors:
                return response
            raise error_from_response(response)

        if retry:
            return self._retry(execute)
        return execute()

    def _retry(self, operation: Callable[[], V20Response]) -> V20Response:
        if self.retry_policy.attempts <= 1:
            return operation()
        return self.retry_policy.retrying()(operation)

    @staticmethod
    def _transport_call(operation: Callable[[], V20Response]) -> V20Response:
        try:
            return operation()
        except V20Timeout as exc:
            raise OandaTimeoutError(
                str(exc),
                url=str(getattr(exc, "url", "") or ""),
                timeout_type=str(getattr(exc, "type", "") or ""),
            ) from exc
        except V20ConnectionError as exc:
            raise OandaConnectionError(
                str(exc),
                url=str(getattr(exc, "url", "") or ""),
            ) from exc
        except ResponseUnexpectedStatus as exc:
            raise error_from_response(exc.response) from exc
        except ResponseNoField as exc:
            raise OandaAdapterError(str(exc)) from exc
