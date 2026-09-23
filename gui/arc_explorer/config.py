"""Configuration loaded from `.env` at the repository root.

Every connection coordinate, guardrail and server binding is read from the
environment. Nothing in this package hardcodes an account, role, warehouse or
row limit; `.env.example` mirrors the full set of variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = Path(__file__).resolve().parent
DATA_DIR = REPO_ROOT / "gui" / "data"


@lru_cache(maxsize=1)
def load_env() -> None:
    """Load `.env` into the process environment, once per process."""
    load_dotenv(REPO_ROOT / ".env")


def log_level() -> str:
    """The configured log level.

    Read separately from `get_settings` so that logging can be set up before
    -- and independently of -- full connection settings validating. A missing
    `SNOWFLAKE_USER` must surface as an actionable message, not as a traceback
    from inside the logger.

    Returns:
        An uppercased level name, defaulting to `INFO`.
    """
    load_env()
    return os.environ.get("ARC_LOG_LEVEL", "INFO").upper()


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"{name} is not set. Copy .env.example to .env and fill it in."
        )
    return value


def _optional(name: str) -> str | None:
    """Return an environment value, or `None` when it is unset or blank."""
    value = os.environ.get(name, "").strip()
    return value or None


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        parsed = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer, got {raw!r}") from exc
    if parsed <= 0:
        raise RuntimeError(f"{name} must be positive, got {parsed}")
    return parsed


@dataclass(frozen=True)
class Settings:
    """Resolved settings for one process."""

    user: str
    account: str
    authenticator: str
    role: str
    warehouse: str
    database: str
    schema: str

    max_rows: int
    default_limit: int
    statement_timeout_seconds: int

    host: str
    port: int
    log_level: str

    # Credentials for the non-browser authenticators. Never logged, never
    # written back to disk, and excluded from the dataclass repr so that
    # printing Settings -- in a traceback, a debugger or a log line -- cannot
    # leak them.
    password: str | None = field(default=None, repr=False)
    passcode: str | None = field(default=None, repr=False)
    private_key_file: str | None = field(default=None)
    private_key_file_pwd: str | None = field(default=None, repr=False)
    token: str | None = field(default=None, repr=False)
    oauth_client_id: str | None = field(default=None)
    oauth_client_secret: str | None = field(default=None, repr=False)
    oauth_redirect_uri: str | None = field(default=None)

    @property
    def schema_cache_path(self) -> Path:
        """Where the introspected schema is cached on disk."""
        return DATA_DIR / "schema_cache.json"

    @property
    def qualified_schema(self) -> str:
        """Fully qualified schema name, e.g. `ARCDW_PROD.DATA_EXCHANGE_LAYER`."""
        return f"{self.database}.{self.schema}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load and validate settings once per process."""
    load_env()

    return Settings(
        user=_require("SNOWFLAKE_USER"),
        account=_require("SNOWFLAKE_ACCOUNT"),
        authenticator=os.environ.get("SNOWFLAKE_AUTHENTICATOR", "externalbrowser")
        .strip()
        .lower(),
        role=_require("SNOWFLAKE_ROLE"),
        warehouse=_require("SNOWFLAKE_WAREHOUSE"),
        database=_require("SNOWFLAKE_DATABASE"),
        schema=_require("SNOWFLAKE_SCHEMA"),
        max_rows=_int_env("ARC_MAX_ROWS", 5_000),
        default_limit=_int_env("ARC_DEFAULT_LIMIT", 500),
        statement_timeout_seconds=_int_env("ARC_STATEMENT_TIMEOUT_SECONDS", 120),
        host=os.environ.get("ARC_HOST", "127.0.0.1"),
        port=_int_env("ARC_PORT", 8787),
        log_level=log_level(),
        password=_optional("SNOWFLAKE_PASSWORD"),
        passcode=_optional("SNOWFLAKE_PASSCODE"),
        private_key_file=_optional("SNOWFLAKE_PRIVATE_KEY_FILE"),
        private_key_file_pwd=_optional("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE"),
        token=_optional("SNOWFLAKE_TOKEN"),
        oauth_client_id=_optional("SNOWFLAKE_OAUTH_CLIENT_ID"),
        oauth_client_secret=_optional("SNOWFLAKE_OAUTH_CLIENT_SECRET"),
        oauth_redirect_uri=_optional("SNOWFLAKE_OAUTH_REDIRECT_URI"),
    )
