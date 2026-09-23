"""Config-driven connection to the Transition Arc warehouse.

Every coordinate of the connection -- account, role, warehouse, database,
schema, statement timeout -- comes from `Settings`, which reads `.env`. Nothing
here hardcodes a Snowflake identifier, so pointing the tooling at a different
sandbox is an `.env` edit rather than a code change.

Authentication follows `SNOWFLAKE_AUTHENTICATOR`. Browser SSO is the default,
but an account whose identity provider will not sign the user in can switch to
Snowflake's own login, a key pair, or a programmatic access token by editing
`.env` alone -- see `AUTHENTICATORS` for the variable each one needs.

Secrets are read from the environment at connect time, handed straight to the
connector, and never logged, echoed or written back to disk.
"""

from __future__ import annotations

import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import snowflake.connector
from snowflake.connector import SnowflakeConnection

from arc_explorer.config import Settings, get_settings
from arc_explorer.logger import get_logger

LOGGER = get_logger("connection")

# Tags the session in Snowflake's query history so Arc can attribute usage.
APPLICATION_NAME = "arc_explorer"

# One round trip that reports what the warehouse thinks this session is.
SESSION_SQL = """
SELECT CURRENT_USER(), CURRENT_ROLE(), CURRENT_WAREHOUSE(),
       CURRENT_DATABASE(), CURRENT_SCHEMA(), CURRENT_ACCOUNT(),
       CURRENT_REGION(), CURRENT_VERSION()
"""

TABLE_COUNT_SQL = """
SELECT COUNT(*)
FROM {database}.information_schema.tables
WHERE table_schema = %s
"""


# Authenticators this project supports, each mapped to the `.env` variable
# that carries its secret (None where the flow is interactive). The connector
# uppercases these names itself, so `.env` may use either case.
AUTHENTICATORS: dict[str, tuple[str | None, str]] = {
    "externalbrowser": (None, "Single sign-on through your browser"),
    "snowflake": ("SNOWFLAKE_PASSWORD", "Snowflake's own username and password"),
    "username_password_mfa": (
        "SNOWFLAKE_PASSWORD",
        "Snowflake password plus multi-factor authentication",
    ),
    "snowflake_jwt": (
        "SNOWFLAKE_PRIVATE_KEY_FILE",
        "Key pair (no browser, Snowflake's recommendation for scripts)",
    ),
    "programmatic_access_token": ("SNOWFLAKE_TOKEN", "Programmatic access token"),
    "oauth": ("SNOWFLAKE_TOKEN", "OAuth access token"),
    "oauth_authorization_code": (
        "SNOWFLAKE_OAUTH_CLIENT_ID",
        "Browser OAuth against Snowflake -- the flow that can use a passkey",
    ),
}


# Snowflake error codes worth translating: the connector's own wording sends
# the reader to the wrong place. Each maps to what actually has to change, and
# by whom.
ERROR_HINTS: dict[str, str] = {
    "390432": (
        "The token is valid, but Snowflake requires a network policy on your\n"
        "user before a programmatic access token may be used. Only an Arc\n"
        "account admin can add one:\n"
        "    CREATE NETWORK POLICY <name> ALLOWED_IP_LIST = ('<your IP>');\n"
        "    ALTER USER <you> SET NETWORK_POLICY = <name>;\n"
        "  or, to drop the requirement instead:\n"
        "    ALTER AUTHENTICATION POLICY <policy>\n"
        "      SET PAT_POLICY = (NETWORK_POLICY_EVALUATION = NOT_ENFORCED);"
    ),
    "390303": (
        "Snowflake did not accept this as an OAuth token. A programmatic\n"
        "access token is not an OAuth token -- try\n"
        "    ./arc.command --authenticator programmatic_access_token"
    ),
    "390100": (
        "Snowflake rejected the username or password. A user provisioned for\n"
        "single sign-on often has no Snowflake password at all; ask Arc."
    ),
    "250001": (
        "The account name in .env may be wrong, or the network is blocking\n"
        "the connection."
    ),
}


def hint_for(message: str) -> str | None:
    """Return guidance for a Snowflake error, matched on its numeric code.

    Args:
        message: The connector's error text, which begins with the code.

    Returns:
        Actionable guidance, or `None` when the code is not one we translate.
    """
    for code, hint in ERROR_HINTS.items():
        if message.startswith(code) or f"{code} (" in message:
            return hint
    return None


class ConnectionFailed(RuntimeError):
    """Raised when the warehouse cannot be reached or the session is unusable."""


class CredentialMissing(RuntimeError):
    """Raised when the chosen authenticator has no credential to work with.

    Distinct from `ConnectionFailed` because it is an `.env` problem the user
    can fix without ever reaching the network.
    """


@dataclass(frozen=True)
class SessionInfo:
    """What the warehouse reports back about an established session.

    Every field is the warehouse's own answer, not the value requested from
    `.env`. Comparing the two is how `describe_mismatches` catches a role or
    warehouse that was silently not applied.
    """

    user: str
    role: str
    warehouse: str
    database: str
    schema: str
    account: str
    region: str
    snowflake_version: str
    table_count: int | None
    elapsed_seconds: float


def _require_credential(value: str | None, variable: str, authenticator: str) -> str:
    """Return a credential, or explain which `.env` line is missing."""
    if value:
        return value
    raise CredentialMissing(
        f"SNOWFLAKE_AUTHENTICATOR={authenticator} needs {variable}, "
        f"which is not set in .env."
    )


def auth_params(settings: Settings) -> dict[str, Any]:
    """Build the authentication half of the connector arguments.

    Pure apart from checking that a named key file exists, so each
    authenticator's wiring stays testable without a warehouse.

    Args:
        settings: Resolved settings for this process.

    Returns:
        Connector keyword arguments carrying the credential.

    Raises:
        CredentialMissing: The authenticator is unknown, or the credential it
            needs is absent from `.env`.
    """
    auth = settings.authenticator

    if auth not in AUTHENTICATORS:
        supported = ", ".join(sorted(AUTHENTICATORS))
        raise CredentialMissing(
            f"SNOWFLAKE_AUTHENTICATOR={auth or '(empty)'} is not supported. "
            f"Use one of: {supported}."
        )

    if auth == "externalbrowser":
        # Cache the SSO token so the browser dance happens once a day, not
        # once a query.
        return {
            "authenticator": auth,
            "client_store_temporary_credential": True,
        }

    if auth in ("snowflake", "username_password_mfa"):
        params: dict[str, Any] = {
            "authenticator": auth,
            "password": _require_credential(
                settings.password, "SNOWFLAKE_PASSWORD", auth
            ),
        }
        if auth == "username_password_mfa":
            # Cache the MFA token so only the first login prompts the device.
            params["client_request_mfa_token"] = True
        if settings.passcode:
            params["passcode"] = settings.passcode
        return params

    if auth == "snowflake_jwt":
        raw = _require_credential(
            settings.private_key_file, "SNOWFLAKE_PRIVATE_KEY_FILE", auth
        )
        key_path = Path(raw).expanduser()
        if not key_path.is_file():
            raise CredentialMissing(
                f"SNOWFLAKE_PRIVATE_KEY_FILE points at {key_path}, "
                f"which does not exist."
            )
        params = {"authenticator": auth, "private_key_file": str(key_path)}
        if settings.private_key_file_pwd:
            params["private_key_file_pwd"] = settings.private_key_file_pwd
        return params

    if auth == "oauth_authorization_code":
        # The driver opens a browser at Snowflake's own /oauth/authorize, so
        # whatever that page accepts -- including a passkey as second factor
        # -- signs the session in. The client id comes from a security
        # integration that only an account admin can create.
        params = {
            "authenticator": auth,
            "oauth_client_id": _require_credential(
                settings.oauth_client_id, "SNOWFLAKE_OAUTH_CLIENT_ID", auth
            ),
        }
        if settings.oauth_client_secret:
            params["oauth_client_secret"] = settings.oauth_client_secret
        if settings.oauth_redirect_uri:
            params["oauth_redirect_uri"] = settings.oauth_redirect_uri
        return params

    # programmatic_access_token and oauth both authenticate with a bare token.
    return {
        "authenticator": auth,
        "token": _require_credential(settings.token, "SNOWFLAKE_TOKEN", auth),
    }


def connection_params(settings: Settings) -> dict[str, Any]:
    """Build the keyword arguments for `snowflake.connector.connect`.

    Args:
        settings: Resolved settings for this process.

    Returns:
        Keyword arguments accepted by `snowflake.connector.connect`: the
        warehouse coordinates from `.env`, the statement timeout as a session
        parameter, and whatever the chosen authenticator needs.

    Raises:
        CredentialMissing: The authenticator has no usable credential.
    """
    params: dict[str, Any] = {
        "user": settings.user,
        "account": settings.account,
        "role": settings.role,
        "warehouse": settings.warehouse,
        "database": settings.database,
        "schema": settings.schema,
        "application": APPLICATION_NAME,
        "session_parameters": {
            "STATEMENT_TIMEOUT_IN_SECONDS": settings.statement_timeout_seconds,
        },
    }
    params.update(auth_params(settings))
    return params


def describe_authenticator(settings: Settings) -> str:
    """A one-line, secret-free description of how this session will sign in."""
    _, description = AUTHENTICATORS.get(
        settings.authenticator, (None, "Unknown authenticator")
    )
    return f"{settings.authenticator} -- {description}"


@contextmanager
def arc_connection(settings: Settings | None = None) -> Iterator[SnowflakeConnection]:
    """Open a connection to the Arc warehouse and close it on the way out.

    With the default `externalbrowser` authenticator this blocks while the user
    completes SSO in their browser.

    Args:
        settings: Settings to connect with; loaded from `.env` when omitted.

    Yields:
        An open Snowflake connection.

    Raises:
        ConnectionFailed: The connector could not establish a session.
    """
    resolved = settings or get_settings()
    # Built before the log line so a credential problem is reported as such,
    # rather than as a connection that was attempted and failed.
    params = connection_params(resolved)
    LOGGER.info(
        "Connecting to %s as %s (role %s, warehouse %s, auth %s)",
        resolved.qualified_schema,
        resolved.user,
        resolved.role,
        resolved.warehouse,
        resolved.authenticator,
    )

    try:
        conn = snowflake.connector.connect(**params)
    except Exception as exc:
        raise ConnectionFailed(str(exc)) from exc

    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception:
            LOGGER.debug("Ignoring error while closing the connection", exc_info=True)
        LOGGER.debug("Connection closed")


def fetch_rows(
    conn: SnowflakeConnection,
    sql: str,
    params: Sequence[Any] | None = None,
) -> list[tuple[Any, ...]]:
    """Run a statement and return its rows as tuples.

    Used for small metadata queries where a DataFrame would be overhead.

    Args:
        conn: An open connection.
        sql: Statement to execute.
        params: Values bound to `%s` placeholders in `sql`.

    Returns:
        All result rows.
    """
    cur = conn.cursor()
    try:
        cur.execute(sql, params)
        rows = cur.fetchall()
        LOGGER.debug("fetch_rows returned %d rows (query_id=%s)", len(rows), cur.sfqid)
        return rows
    finally:
        cur.close()


def fetch_dataframe(conn: SnowflakeConnection, sql: str) -> Any:
    """Run a statement and return its rows as a pandas DataFrame.

    Args:
        conn: An open connection.
        sql: Statement to execute.

    Returns:
        A `pandas.DataFrame` of the full result set.
    """
    cur = conn.cursor()
    try:
        cur.execute(sql)
        frame = cur.fetch_pandas_all()
        LOGGER.debug(
            "fetch_dataframe returned %d rows x %d cols (query_id=%s)",
            frame.shape[0],
            frame.shape[1],
            cur.sfqid,
        )
        return frame
    finally:
        cur.close()


def inspect_session(
    conn: SnowflakeConnection,
    settings: Settings,
    *,
    started_at: float | None = None,
) -> SessionInfo:
    """Ask the warehouse what this session is, and how much it can see.

    The table count is a reachability probe for the configured schema. A role
    without `information_schema` visibility leaves it `None` rather than
    failing the whole check -- the session itself is still usable.

    Args:
        conn: An open connection.
        settings: Settings the connection was built from.
        started_at: `time.monotonic()` reading from before the connection was
            opened, so the reported elapsed time includes SSO. Defaults to now.

    Returns:
        The warehouse's own view of the session.

    Raises:
        ConnectionFailed: The session query returned nothing.
    """
    begin = time.monotonic() if started_at is None else started_at

    rows = fetch_rows(conn, SESSION_SQL)
    if not rows:
        raise ConnectionFailed("The warehouse returned no session information.")
    row = rows[0]

    table_count: int | None
    try:
        count_rows = fetch_rows(
            conn,
            TABLE_COUNT_SQL.format(database=settings.database),
            (settings.schema,),
        )
        table_count = int(count_rows[0][0]) if count_rows else None
    except Exception:  # noqa: BLE001 - a blind role is a warning, not a failure
        LOGGER.warning(
            "Could not read information_schema for %s; the session is still open.",
            settings.qualified_schema,
        )
        table_count = None

    info = SessionInfo(
        user=str(row[0]),
        role=str(row[1]),
        warehouse=str(row[2]),
        database=str(row[3]),
        schema=str(row[4]),
        account=str(row[5]),
        region=str(row[6]),
        snowflake_version=str(row[7]),
        table_count=table_count,
        elapsed_seconds=time.monotonic() - begin,
    )
    LOGGER.info(
        "Session established in %.1fs; %s tables visible in %s",
        info.elapsed_seconds,
        "unknown" if info.table_count is None else info.table_count,
        settings.qualified_schema,
    )
    return info


def describe_mismatches(info: SessionInfo, settings: Settings) -> list[str]:
    """Report where the live session differs from what `.env` asked for.

    Snowflake silently falls back when a requested role or warehouse is not
    granted, so a connection can succeed while reading the wrong thing.

    Args:
        info: What the warehouse reported.
        settings: What `.env` requested.

    Returns:
        One human-readable line per mismatch; empty when the session matches.
    """
    expected = (
        ("role", settings.role, info.role),
        ("warehouse", settings.warehouse, info.warehouse),
        ("database", settings.database, info.database),
        ("schema", settings.schema, info.schema),
    )
    return [
        f"{label} is {actual or 'unset'}, but .env asks for {wanted}"
        for label, wanted, actual in expected
        if (actual or "").upper() != wanted.upper()
    ]
