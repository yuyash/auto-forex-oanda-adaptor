"""HTTP transport and retry policy for OANDA REST calls."""

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
from oanda.config import OandaSettings
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


class OandaTransport:
    """Low-level REST transport for the OANDA REST v20 API."""

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
            body=OandaTransport._json_body(body),
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
