"""Account management implementation backed by OANDA v20."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from core import (
    Account,
    AccountId,
    AccountManager,
    AccountSummary,
    CurrencyPair,
    Metadata,
)

import oanda.payload as payload
from oanda.config import OandaSettings
from oanda.constants import OANDA_PROVIDER
from oanda.errors import ensure_success
from oanda.gateway import OandaGateway
from oanda.mappers import OandaAccountMapper


class OandaAccountManager(AccountManager):
    """Account manager port implementation backed by OANDA v20."""

    def __init__(
        self,
        *,
        gateway: OandaGateway,
        mapper: OandaAccountMapper | None = None,
    ) -> None:
        self.gateway = gateway
        self.mapper = mapper or OandaAccountMapper()

    @classmethod
    def from_settings(cls, settings: OandaSettings) -> OandaAccountManager:
        """Create an OANDA account manager from settings."""
        return cls(
            gateway=OandaGateway.from_settings(settings),
        )

    def list_accounts(self) -> tuple[Account, ...]:
        """Return accounts authorized for the configured token."""
        response = ensure_success(self.gateway.list_accounts(), 200)
        accounts = self._get(response.body, "accounts", ()) or ()
        return tuple(self.mapper.account_from_properties(account) for account in accounts)

    def get_account(self, account_id: AccountId) -> Account:
        """Return a full OANDA account as a Core account reference."""
        response = ensure_success(self.gateway.get_account(str(account_id)), 200)
        account = self._get(response.body, "account")
        return self.mapper.account_from_properties(account)

    def get_account_summary(self, account_id: AccountId) -> AccountSummary:
        """Return an OANDA account summary as a Core account summary."""
        response = ensure_success(
            self.gateway.get_account_summary(str(account_id)),
            200,
        )
        return self.mapper.summary_from_response(response)

    def get_account_instruments(self, account_id: AccountId) -> tuple[CurrencyPair, ...]:
        """Return tradable instruments for an account."""
        response = ensure_success(
            self.gateway.get_account_instruments(str(account_id)),
            200,
        )
        items = self._get(response.body, "instruments", ()) or ()
        return tuple(
            pair
            for item in items
            if (pair := self._currency_pair_or_none(self._get(item, "name"))) is not None
        )

    def configure_account(
        self,
        account_id: AccountId,
        *,
        alias: str | None = None,
        margin_rate: Decimal | None = None,
    ) -> Account:
        """Update OANDA account alias or margin rate."""
        request: dict[str, str] = {}
        if alias is not None:
            request["alias"] = alias
        if margin_rate is not None:
            request["marginRate"] = str(margin_rate)
        response = ensure_success(
            self.gateway.configure_account(str(account_id), request, retry=True),
            200,
        )
        body = self._metadata(response.body)
        return Account(
            id=account_id,
            provider=OANDA_PROVIDER,
            alias=alias,
            metadata=body,
        )

    def get_account_changes(
        self,
        account_id: AccountId,
        *,
        since_transaction_id: str,
    ) -> Metadata:
        """Return raw OANDA account changes metadata."""
        response = ensure_success(
            self.gateway.get_account_changes(
                str(account_id),
                {"sinceTransactionID": since_transaction_id},
            ),
            200,
        )
        return self._metadata(response.body)

    @staticmethod
    def _metadata(value: Any) -> Metadata:
        return payload.metadata(value)

    @staticmethod
    def _get(value: Any, key: str, default: Any = None) -> Any:
        return payload.get(value, key, default)

    @staticmethod
    def _currency_pair_or_none(value: Any) -> CurrencyPair | None:
        if value is None:
            return None
        try:
            return CurrencyPair.of(str(value))
        except ValueError:
            return None
