"""OANDA adapter settings."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class OandaEnvironment(StrEnum):
    """Known OANDA environments."""

    PRACTICE = "practice"
    LIVE = "live"


def default_hostname_for_environment(environment: OandaEnvironment) -> str:
    """Return the default OANDA hostname for an environment."""
    if environment == OandaEnvironment.LIVE:
        return "api-fxtrade.oanda.com"
    return "api-fxpractice.oanda.com"


class OandaSettings(BaseSettings):
    """Runtime settings for OANDA v20 access."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="OANDA_",
        extra="ignore",
    )

    account_id: str = Field(min_length=1)
    access_token: SecretStr
    environment: OandaEnvironment = OandaEnvironment.PRACTICE
    hostname: str | None = None
    port: int = Field(default=443, gt=0)
    ssl: bool = True
    application: str = "AutoForexV2"
    poll_timeout: int = Field(default=10, gt=0)
    stream_timeout: int = Field(default=60, gt=0)
    stream_chunk_size: int = Field(default=512, gt=0)
    retry_attempts: int = Field(default=3, ge=1)
    retry_initial_seconds: float = Field(default=0.25, ge=0)
    retry_max_seconds: float = Field(default=4.0, ge=0)
    retry_multiplier: float = Field(default=2.0, ge=1)

    @computed_field
    @property
    def resolved_hostname(self) -> str:
        """Return the explicit hostname or the default for the environment."""
        if self.hostname:
            return self.hostname
        return default_hostname_for_environment(self.environment)
