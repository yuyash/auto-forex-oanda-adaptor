"""Account management implementation backed by OANDA v20."""

from __future__ import annotations

from typing import Any, Protocol

from core import (
    Account,
    AccountId,
    AccountManager,
    AccountSummary,
    CurrencyPair,
    MarginRate,
    Metadata,
)

import oanda.models as om
from oanda.config import OandaSettings
from oanda.constants import OANDA_PROVIDER
from oanda.errors import OandaResponsePolicy
from oanda.gateway import OandaGateway
from oanda.mappers import OandaAccountMapper, OandaInstrumentMapper
from oanda.payload import OandaPayload as payload


class OandaAccountGateway(Protocol):
    """Gateway methods required by the account manager."""

    def list_accounts(self) -> Any: ...
    def get_account(self, account_id: str) -> Any: ...
    def get_account_summary(self, account_id: str) -> Any: ...
    def get_account_instruments(self, account_id: str) -> Any: ...
    def configure_account(
        self,
        account_id: str,
        request: Any = None,
        *,
        retry: bool = False,
        **kwargs: Any,
    ) -> Any: ...
    def get_account_changes(self, account_id: str, request: Any = None) -> Any: ...


class OandaAccountManager(AccountManager):
    """Account manager port implementation backed by OANDA v20."""

    def __init__(
        self,
        *,
        gateway: OandaAccountGateway,
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
        response = OandaResponsePolicy.ensure_success(self.gateway.list_accounts(), 200)
        accounts = payload.get(response.body, "accounts", ()) or ()
        return tuple(self.mapper.account_from_properties(account) for account in accounts)

    def get_account(self, account_id: AccountId) -> Account:
        """Return a full OANDA account as a Core account reference."""
        response = OandaResponsePolicy.ensure_success(
            self.gateway.get_account(str(account_id)), 200
        )
        account = payload.get(response.body, "account")
        return self.mapper.account_from_properties(account)

    def get_account_summary(self, account_id: AccountId) -> AccountSummary:
        """Return an OANDA account summary as a Core account summary."""
        response = OandaResponsePolicy.ensure_success(
            self.gateway.get_account_summary(str(account_id)),
            200,
        )
        return self.mapper.summary_from_response(response)

    def get_account_instruments(self, account_id: AccountId) -> tuple[CurrencyPair, ...]:
        """Return tradable instruments for an account."""
        response = OandaResponsePolicy.ensure_success(
            self.gateway.get_account_instruments(str(account_id)),
            200,
        )
        items = payload.get(response.body, "instruments", ()) or ()
        return tuple(
            pair
            for item in items
            if (pair := OandaInstrumentMapper.to_core_or_none(payload.get(item, "name")))
            is not None
        )

    def configure_account(
        self,
        account_id: AccountId,
        *,
        alias: str | None = None,
        margin_rate: MarginRate | None = None,
    ) -> Account:
        """Update OANDA account alias or margin rate."""
        request: dict[str, str] = {}
        if alias is not None:
            request["alias"] = alias
        if margin_rate is not None:
            request["marginRate"] = str(margin_rate)
        response = OandaResponsePolicy.ensure_success(
            self.gateway.configure_account(
                str(account_id),
                om.ConfigureAccountRequest.model_validate(request),
                retry=True,
            ),
            200,
        )
        body = payload.metadata(response.body)
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
        response = OandaResponsePolicy.ensure_success(
            self.gateway.get_account_changes(
                str(account_id),
                om.AccountChangesRequest.model_validate(
                    {"sinceTransactionID": since_transaction_id}
                ),
            ),
            200,
        )
        return payload.metadata(response.body)
