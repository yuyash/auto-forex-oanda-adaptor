"""HTTP request construction and IO for the OANDA transport."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request

import oanda.models as om
from oanda.errors import OandaConnectionError, OandaResponsePolicy, OandaTimeoutError
from oanda.transport_codecs import OandaTransportCodec


@dataclass(frozen=True, slots=True)
class OandaUrlBuilder:
    """Build REST and streaming OANDA endpoint URLs."""

    hostname: str
    stream_hostname: str
    port: int = 443
    ssl: bool = True

    def url(self, path: str, *, query: Any = None, stream: bool = False) -> str:
        """Return a complete endpoint URL."""
        scheme = "https" if self.ssl else "http"
        hostname = self.stream_hostname if stream else self.hostname
        default_port = 443 if self.ssl else 80
        netloc = hostname if self.port == default_port else f"{hostname}:{self.port}"
        query_values = OandaTransportCodec.query_dump(query)
        suffix = f"?{urlencode(query_values)}" if query_values else ""
        return f"{scheme}://{netloc}{path}{suffix}"


@dataclass(frozen=True, slots=True)
class OandaRequestFactory:
    """Build authenticated urllib requests for OANDA."""

    access_token: str
    application: str = "AutoForexV2"

    def request(self, method: str, url: str, *, body: Any) -> Request:
        """Return a urllib request with OANDA headers and optional JSON body."""
        payload = None
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.access_token}",
            "User-Agent": self.application,
        }
        if body is not None:
            payload = json.dumps(
                OandaTransportCodec.jsonable(OandaTransportCodec.model_dump(body)),
                separators=(",", ":"),
            ).encode()
            headers["Content-Type"] = "application/json"
        return Request(url, data=payload, headers=headers, method=method)


class OandaResponseReader:
    """Read urllib response objects into OANDA response wrappers."""

    @classmethod
    def http_response(cls, response: Any, *, url: str) -> om.OandaHttpResponse:
        """Read a finite HTTP response body."""
        body = response.read()
        return om.OandaHttpResponse(
            status=int(getattr(response, "status", getattr(response, "code", 0))),
            reason=str(getattr(response, "reason", "") or ""),
            headers=dict(response.headers.items()),
            body=OandaTransportCodec.json_body(body),
            raw_body=body,
            url=url,
            content_type=response.headers.get("Content-Type"),
        )

    @classmethod
    def stream_response(
        cls,
        response: Any,
        *,
        url: str,
        stream_kind: str,
    ) -> om.OandaStreamResponse:
        """Wrap an open urllib streaming response."""
        return om.OandaStreamResponse(
            status=int(getattr(response, "status", getattr(response, "code", 0))),
            reason=str(getattr(response, "reason", "") or ""),
            headers=dict(response.headers.items()),
            stream=response,
            url=url,
            content_type=response.headers.get("Content-Type"),
            stream_kind=stream_kind,
        )

    @classmethod
    def http_error_response(cls, error: HTTPError, *, url: str) -> om.OandaHttpResponse:
        """Read an HTTPError body as a normal OANDA HTTP response."""
        body = error.read()
        return om.OandaHttpResponse(
            status=int(error.code),
            reason=str(error.reason),
            headers=dict(error.headers.items()),
            body=OandaTransportCodec.json_body(body),
            raw_body=body,
            url=url,
            content_type=error.headers.get("Content-Type"),
        )


class OandaHttpClient:
    """Perform non-streaming and streaming OANDA HTTP requests."""

    def __init__(
        self,
        *,
        opener: Any,
        urls: OandaUrlBuilder,
        requests: OandaRequestFactory,
        poll_timeout: timedelta,
        stream_timeout: timedelta,
    ) -> None:
        self.opener = opener
        self.urls = urls
        self.requests = requests
        self.poll_timeout = poll_timeout
        self.stream_timeout = stream_timeout

    def send(
        self,
        method: str,
        path: str,
        *,
        query: Any = None,
        body: Any = None,
    ) -> om.OandaHttpResponse:
        """Send one finite OANDA request."""
        url = self.urls.url(path, query=query)
        request = self.requests.request(method, url, body=body)
        try:
            response = self.opener.open(request, timeout=self.poll_timeout.total_seconds())
            return OandaResponseReader.http_response(response, url=url)
        except HTTPError as exc:
            return OandaResponseReader.http_response(exc, url=url)
        except TimeoutError as exc:
            raise OandaTimeoutError(str(exc), url=url, timeout_type="read") from exc
        except URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise OandaTimeoutError(str(exc.reason), url=url, timeout_type="connect") from exc
            raise OandaConnectionError(str(exc.reason), url=url) from exc

    def open_stream(
        self,
        method: str,
        path: str,
        *,
        query: Any = None,
        stream_kind: str,
    ) -> om.OandaStreamResponse:
        """Open a streaming OANDA request."""
        url = self.urls.url(path, query=query, stream=True)
        request = self.requests.request(method, url, body=None)
        try:
            response = self.opener.open(request, timeout=self.stream_timeout.total_seconds())
        except HTTPError as exc:
            raw = OandaResponseReader.http_error_response(exc, url=url)
            raise OandaResponsePolicy.error_from_response(
                om.OandaResponse(raw=raw, body=raw.body)
            ) from exc
        except TimeoutError as exc:
            raise OandaTimeoutError(str(exc), url=url, timeout_type="stream") from exc
        except URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise OandaTimeoutError(str(exc.reason), url=url, timeout_type="connect") from exc
            raise OandaConnectionError(str(exc.reason), url=url) from exc

        return OandaResponseReader.stream_response(
            response,
            url=url,
            stream_kind=stream_kind,
        )
