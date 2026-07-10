from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

from core import Account, AccountId, AccountSummary, CurrencyPair, MarginRate, Metadata

import oanda.models as om
from oanda import OANDA_PROVIDER
from oanda.accounts import OandaAccountManager
from tests.support import FakeResponse


class TestAccounts:
    def test_account_manager_delegates_account_reads_to_gateway_and_mapper(self) -> None:
        gateway = Mock()
        mapper = Mock()
        account = Account(id=AccountId.of("001"), provider=OANDA_PROVIDER)
        summary = AccountSummary.model_validate({"account_id": "001", "currency": "USD"})
        gateway.list_accounts.return_value = FakeResponse(
            200,
            {"accounts": [SimpleNamespace(id="001")]},
        )
        gateway.get_account.return_value = FakeResponse(200, {"account": SimpleNamespace(id="001")})
        gateway.get_account_summary.return_value = FakeResponse(200, {"account": {}})
        mapper.account_from_properties.return_value = account
        mapper.summary_from_response.return_value = summary
        account_id = AccountId.of("001")
        manager = OandaAccountManager(gateway=gateway, mapper=mapper)

        assert manager.list_accounts() == (account,)
        assert manager.get_account(account_id) == account
        assert manager.get_account_summary(account_id) == summary
        gateway.list_accounts.assert_called_once_with()
        gateway.get_account.assert_called_once_with("001")
        gateway.get_account_summary.assert_called_once_with("001")

    def test_account_manager_builds_instruments_and_configuration_requests(self) -> None:
        gateway = Mock()
        mapper = Mock()
        gateway.get_account_instruments.return_value = FakeResponse(
            200,
            {
                "instruments": [
                    SimpleNamespace(name="USD_JPY"),
                    SimpleNamespace(name="EUR_USD"),
                ]
            },
        )
        gateway.configure_account.return_value = FakeResponse(
            200,
            {"lastTransactionID": "10"},
        )
        account_id = AccountId.of("001")
        manager = OandaAccountManager(gateway=gateway, mapper=mapper)

        instruments = manager.get_account_instruments(account_id)
        configured = manager.configure_account(
            account_id,
            alias="primary",
            margin_rate=MarginRate("0.03"),
        )

        assert instruments == (CurrencyPair.of("USD_JPY"), CurrencyPair.of("EUR_USD"))
        gateway.get_account_instruments.assert_called_once_with("001")
        gateway.configure_account.assert_called_once_with(
            "001",
            om.ConfigureAccountRequest.model_validate({"alias": "primary", "marginRate": "0.03"}),
            retry=True,
        )
        assert configured.provider == OANDA_PROVIDER
        assert configured.metadata == Metadata.of(lastTransactionID="10")

    def test_account_manager_get_account_changes_returns_metadata(self) -> None:
        gateway = Mock()
        mapper = Mock()
        gateway.get_account_changes.return_value = FakeResponse(
            200,
            {"lastTransactionID": "11", "state": {"NAV": "1000"}},
        )
        account_id = AccountId.of("001")
        manager = OandaAccountManager(gateway=gateway, mapper=mapper)

        changes = manager.get_account_changes(account_id, since_transaction_id="10")

        gateway.get_account_changes.assert_called_once_with(
            "001",
            om.AccountChangesRequest.model_validate({"sinceTransactionID": "10"}),
        )
        assert changes["lastTransactionID"] == "11"
