from __future__ import annotations

from oanda import (
    OandaAccountManager,
    OandaBroker,
    OandaDataSource,
    OandaGateway,
    OandaProvider,
)


def test_public_imports_are_available_from_package_root() -> None:
    assert OandaAccountManager.__name__ == "OandaAccountManager"
    assert OandaBroker.__name__ == "OandaBroker"
    assert OandaDataSource.__name__ == "OandaDataSource"
    assert OandaGateway.__name__ == "OandaGateway"
    assert OandaProvider.__name__ == "OandaProvider"
