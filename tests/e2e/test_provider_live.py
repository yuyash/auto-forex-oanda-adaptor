from __future__ import annotations

from typing import cast

from core import AccountId

from oanda import OandaAccountManager, OandaBroker, OandaDataSource, OandaProvider, OandaSettings


def test_live_provider_bundles_services_and_reaches_account_summary(
    oanda_provider: OandaProvider,
    oanda_settings: OandaSettings,
) -> None:
    summary = oanda_provider.accounts.get_account_summary(AccountId.of(oanda_settings.account_id))
    account_manager = cast(OandaAccountManager, oanda_provider.account_manager)
    broker = cast(OandaBroker, oanda_provider.broker)
    data_source = cast(OandaDataSource, oanda_provider.data_source)

    assert account_manager.gateway is broker.gateway
    assert data_source.gateway is broker.gateway
    assert summary.account_id.value == oanda_settings.account_id
