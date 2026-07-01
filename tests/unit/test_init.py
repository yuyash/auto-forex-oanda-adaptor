from __future__ import annotations

import oanda


def test_package_exports_public_adapter_api() -> None:
    for name in (
        "OandaAccountManager",
        "OandaBroker",
        "OandaDataSource",
        "OandaGateway",
        "OandaProvider",
        "OandaSettings",
    ):
        assert name in oanda.__all__
        assert getattr(oanda, name).__name__ == name
