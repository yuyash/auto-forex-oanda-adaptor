from __future__ import annotations

from core import AccountId

from oanda import OandaProvider, OandaSettings


class TestAccountsLive:
    def test_live_account_manager_readonly_apis(
        self,
        oanda_provider: OandaProvider,
        oanda_settings: OandaSettings,
    ) -> None:
        account_id = AccountId.of(oanda_settings.account_id)
        accounts = oanda_provider.accounts.list_accounts()
        account = oanda_provider.accounts.get_account(account_id)
        summary = oanda_provider.accounts.get_account_summary(account_id)
        instruments = oanda_provider.accounts.get_account_instruments(account_id)
        changes = oanda_provider.accounts.get_account_changes(
            account_id,
            since_transaction_id=summary.last_transaction_id or "1",
        )

        assert any(item.id.value == oanda_settings.account_id for item in accounts)
        assert account.id.value == oanda_settings.account_id
        assert summary.account_id.value == oanda_settings.account_id
        assert instruments
        assert "lastTransactionID" in changes
