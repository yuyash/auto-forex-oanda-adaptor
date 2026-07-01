from __future__ import annotations

import pytest

from oanda.errors import (
    OandaAuthenticationError,
    OandaBadRequestError,
    OandaRateLimitError,
    OandaServerError,
    ensure_success,
    error_from_response,
    is_retryable_response_status,
    response_status_code,
)
from tests.support import FakeResponse


def test_ensure_success_returns_expected_status_and_raises_specific_errors() -> None:
    ok = FakeResponse(200, {"ok": True})
    auth = FakeResponse(401, {"errorCode": "UNAUTHORIZED", "errorMessage": "bad token"})

    assert ensure_success(ok, 200) is ok
    with pytest.raises(OandaAuthenticationError, match="UNAUTHORIZED"):
        ensure_success(auth, 200)


def test_error_from_response_classifies_statuses() -> None:
    assert isinstance(error_from_response(FakeResponse(400, {})), OandaBadRequestError)
    assert isinstance(error_from_response(FakeResponse(429, {})), OandaRateLimitError)
    assert isinstance(error_from_response(FakeResponse(500, {})), OandaServerError)


def test_error_from_response_extracts_transaction_reject_reason() -> None:
    error = error_from_response(
        FakeResponse(
            400,
            {"orderRejectTransaction": {"reason": "INSUFFICIENT_MARGIN"}},
        )
    )

    assert error.error_code == "INSUFFICIENT_MARGIN"
    assert "INSUFFICIENT_MARGIN" in str(error)


def test_retryable_status_and_status_parsing() -> None:
    assert is_retryable_response_status(503)
    assert not is_retryable_response_status(404)
    assert response_status_code(FakeResponse(200, {})) == 200
    assert response_status_code(object()) is None
