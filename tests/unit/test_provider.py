from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from unittest.mock import Mock

import pytest
from core import AccountProvider

import oanda.provider as provider_module
from oanda.gateway import OandaGateway
from oanda.provider import OandaProvider


@dataclass
class AccountManagerFake:
    gateway: object


@dataclass
class AccountBoundServiceFake:
    account_id: str
    gateway: object


def test_oanda_provider_bundles_mocked_services(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(provider_module, "OandaAccountManager", AccountManagerFake)
    monkeypatch.setattr(provider_module, "OandaBroker", AccountBoundServiceFake)
    monkeypatch.setattr(provider_module, "OandaDataSource", AccountBoundServiceFake)
    gateway = object()

    provider = OandaProvider(account_id="001", gateway=cast(OandaGateway, gateway))

    assert provider.provider == AccountProvider.OANDA
    assert provider.account_id == "001"
    assert provider.gateway is gateway
    assert isinstance(provider.account_manager, AccountManagerFake)
    assert isinstance(provider.broker, AccountBoundServiceFake)
    assert isinstance(provider.data_source, AccountBoundServiceFake)
    assert provider.account_manager.gateway is gateway
    assert provider.broker.gateway is gateway
    assert provider.data_source.gateway is gateway


def test_oanda_provider_from_credentials_uses_gateway_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provider_module, "OandaAccountManager", AccountManagerFake)
    monkeypatch.setattr(provider_module, "OandaBroker", AccountBoundServiceFake)
    monkeypatch.setattr(provider_module, "OandaDataSource", AccountBoundServiceFake)
    gateway = object()
    gateway_cls = Mock()
    gateway_cls.from_credentials.return_value = gateway
    monkeypatch.setattr(provider_module, "OandaGateway", gateway_cls)

    provider = OandaProvider.from_credentials(account_id="001", access_token="token")

    assert provider.gateway is gateway
    gateway_cls.from_credentials.assert_called_once()
    call_kwargs: dict[str, Any] = gateway_cls.from_credentials.call_args.kwargs
    assert call_kwargs["access_token"] == "token"
