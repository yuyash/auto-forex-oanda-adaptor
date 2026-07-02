from __future__ import annotations

from typing import cast

from oanda.accounts import OandaAccountManager
from oanda.broker import OandaBroker
from oanda.gateway import OandaGateway
from oanda.provider import OandaProvider
from oanda.source import OandaDataSource
from tests.integration.fakes import IntegrationGateway


class TestProvider:
    def test_provider_integrates_account_broker_and_source_services_without_http(self) -> None:
        gateway = IntegrationGateway()
        provider = OandaProvider(account_id="001", gateway=cast(OandaGateway, gateway))

        assert isinstance(provider.account_manager, OandaAccountManager)
        assert isinstance(provider.broker, OandaBroker)
        assert isinstance(provider.data, OandaDataSource)
        assert provider.account_manager.gateway is gateway
        assert provider.broker.gateway is gateway
        assert provider.data.gateway is gateway
