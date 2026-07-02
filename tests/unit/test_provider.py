from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

import pytest

import oanda.provider as provider_module
from oanda import OANDA_PROVIDER
from oanda.config import OandaSettings
from oanda.gateway import OandaGateway
from oanda.provider import OandaProvider


@dataclass
class AccountManagerFake:
    gateway: object


@dataclass
class AccountBoundServiceFake:
    account_id: str
    gateway: object


class TestProvider:
    def test_oanda_provider_bundles_mocked_services(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(provider_module, "OandaAccountManager", AccountManagerFake)
        monkeypatch.setattr(provider_module, "OandaBroker", AccountBoundServiceFake)
        monkeypatch.setattr(provider_module, "OandaDataSource", AccountBoundServiceFake)
        gateway = object()

        provider = OandaProvider(account_id="001", gateway=cast(OandaGateway, gateway))

        assert provider.provider == OANDA_PROVIDER
        assert provider.account_id == "001"
        assert provider.gateway is gateway
        assert isinstance(provider.account_manager, AccountManagerFake)
        assert isinstance(provider.broker, AccountBoundServiceFake)
        assert isinstance(provider.data, AccountBoundServiceFake)
        assert provider.account_manager.gateway is gateway
        assert provider.broker.gateway is gateway
        assert provider.data.gateway is gateway

    def test_oanda_provider_from_settings_uses_gateway_factory(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(provider_module, "OandaAccountManager", AccountManagerFake)
        monkeypatch.setattr(provider_module, "OandaBroker", AccountBoundServiceFake)
        monkeypatch.setattr(provider_module, "OandaDataSource", AccountBoundServiceFake)
        gateway = object()
        gateway_cls = Mock()
        gateway_cls.from_settings.return_value = gateway
        monkeypatch.setattr(provider_module, "OandaGateway", gateway_cls)
        settings = cast(OandaSettings, SimpleNamespace(account_id="001"))

        provider = OandaProvider.from_settings(settings)

        assert provider.gateway is gateway
        gateway_cls.from_settings.assert_called_once_with(settings)
