"""Connect to the Transition Arc warehouse and report what the session can see.

This is what `arc.command` runs. It is deliberately chatty and forgiving: the
person reading its output may be looking at a Terminal window for the first
time, so every failure names the file to edit or the person to ask.

Exit codes:
    0  connected, and the schema cache is present
    1  the warehouse could not be reached, or the session is unusable
    2  configuration is missing or still holds a placeholder
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "gui"))

from arc_explorer.cli_login import LoginCancelled, cli_login
from arc_explorer.config import Settings, get_settings
from arc_explorer.connection import (
    AUTHENTICATORS,
    ConnectionFailed,
    CredentialMissing,
    arc_connection,
    describe_authenticator,
    describe_mismatches,
    hint_for,
    inspect_session,
)
from arc_explorer.schema_cache import (
    fetch_schema,
    summarise_cache,
    write_schema_cache,
)
from arc_explorer.web_app import serve
from dotenv import dotenv_values

EXIT_OK = 0
EXIT_CONNECTION = 1
EXIT_CONFIG = 2


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="connect.py",
        description="Connect to the Transition Arc warehouse and verify access.",
    )
    parser.add_argument(
        "--refresh-schema",
        action="store_true",
        help="Re-read the table and column catalogue even if a cache exists.",
    )
    parser.add_argument(
        "--no-schema",
        action="store_true",
        help="Only check the connection; never touch the schema cache.",
    )
    parser.add_argument(
        "--authenticator",
        choices=sorted(AUTHENTICATORS),
        help=(
            "Override SNOWFLAKE_AUTHENTICATOR for this run, to try a sign-in "
            "method without editing .env. Any secret it needs must already be "
            "in .env."
        ),
    )
    return parser.parse_args(argv)


def _placeholder_user() -> str | None:
    """The example email in `.env.example`, which `.env` must not still hold."""
    example = REPO_ROOT / ".env.example"
    if not example.exists():
        return None
    return (dotenv_values(example).get("SNOWFLAKE_USER") or "").strip() or None


def _load_settings() -> Settings:
    """Resolve settings, turning configuration problems into exit code 2."""
    if not (REPO_ROOT / ".env").exists():
        print(
            "No .env file found.\n"
            f"  Copy {REPO_ROOT / '.env.example'} to {REPO_ROOT / '.env'} and set "
            "SNOWFLAKE_USER to your work email address.",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_CONFIG)

    try:
        settings = get_settings()
    except RuntimeError as exc:
        print(f"Configuration problem: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_CONFIG) from exc

    placeholder = _placeholder_user()
    if placeholder and settings.user.strip().lower() == placeholder.lower():
        print(
            f"SNOWFLAKE_USER is still the example value ({placeholder}).\n"
            f"  Edit {REPO_ROOT / '.env'} and set it to your own work email address.",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_CONFIG)

    return settings


def _print_authenticator_help(settings: Settings) -> None:
    """List the sign-in methods, so a blocked user can see the way round."""
    print(
        "\nOther ways to sign in, if this one is not available to you:", file=sys.stderr
    )
    for name, (variable, description) in sorted(AUTHENTICATORS.items()):
        if name == settings.authenticator:
            continue
        needs = f" (set {variable} in .env)" if variable else ""
        print(f"  SNOWFLAKE_AUTHENTICATOR={name}{needs}", file=sys.stderr)
        print(f"      {description}", file=sys.stderr)
    print(
        "\nTo try one without editing .env:\n  ./arc.command --authenticator snowflake",
        file=sys.stderr,
    )


def _print_report(info, settings: Settings) -> list[str]:
    """Print the session summary and return any role/warehouse mismatches."""
    visible = "unknown" if info.table_count is None else str(info.table_count)
    fields = (
        ("user", info.user),
        ("role", info.role),
        ("warehouse", info.warehouse),
        ("database", info.database),
        ("schema", info.schema),
        ("account", f"{info.account} ({info.region})"),
        ("snowflake", info.snowflake_version),
        ("tables visible", visible),
    )
    print(f"\nConnected in {info.elapsed_seconds:.1f}s.\n")
    for label, value in fields:
        print(f"  {label:<15} {value}")

    mismatches = describe_mismatches(info, settings)
    if mismatches:
        print("\n  Warning: the session is not what .env asked for --")
        for line in mismatches:
            print(f"    - {line}")
        print("    Ask Arc whether your sandbox grants have changed.")
    return mismatches


def _handle_schema(conn, settings: Settings, args: argparse.Namespace) -> None:
    """Refresh or report on the local schema cache."""
    path = settings.schema_cache_path

    if args.no_schema:
        return

    if path.exists() and not args.refresh_schema:
        try:
            cached = json.loads(path.read_text())
            print(f"\nSchema cache: {summarise_cache(cached)}")
        except (OSError, json.JSONDecodeError):
            print(f"\nSchema cache at {path} is unreadable; refreshing it.")
            write_schema_cache(fetch_schema(conn, settings), path)
        else:
            print("  Run ./arc.command --refresh-schema to re-read it from Snowflake.")
        return

    reason = "refreshing" if path.exists() else "not found, building it"
    print(f"\nSchema cache {reason}...")
    payload = fetch_schema(conn, settings)
    write_schema_cache(payload, path)
    print(f"  {summarise_cache(payload)}")
    print(f"  Written to {path}")


def main(argv: list[str] | None = None) -> int:
    """Run the connection check. Returns the process exit code."""
    args = _parse_args(argv)
    settings = _load_settings()
    if args.authenticator:
        settings = dataclasses.replace(settings, authenticator=args.authenticator)

    if settings.authenticator in ("snowflake", "username_password_mfa"):
        print("Sign in here. Password and MFA code are hidden.")
        try:
            settings = cli_login(settings)
        except LoginCancelled:
            print("Sign-in cancelled. No connection attempted.")
            return EXIT_OK
        except (ValueError, RuntimeError) as exc:
            print(f"Cannot sign in: {exc}", file=sys.stderr)
            return EXIT_CONFIG

    print("Transition Arc connection check")
    print(f"  target    {settings.qualified_schema}")
    print(f"  as        {settings.user}")
    print(f"  sign-in   {describe_authenticator(settings)}")
    if settings.authenticator == "externalbrowser":
        print("\nA browser window will open for single sign-on. Complete it there,")
        print("then come back to this window.")

    started_at = time.monotonic()
    try:
        with arc_connection(settings) as conn:
            info = inspect_session(conn, settings, started_at=started_at)
            mismatches = _print_report(info, settings)
            _handle_schema(conn, settings, args)
            if not args.no_schema:
                serve(conn, settings)
    except CredentialMissing as exc:
        print(f"\nCannot sign in: {exc}", file=sys.stderr)
        print(f"  Edit {REPO_ROOT / '.env'}.", file=sys.stderr)
        _print_authenticator_help(settings)
        return EXIT_CONFIG
    except ConnectionFailed as exc:
        print(f"\nCould not connect to Snowflake:\n  {exc}", file=sys.stderr)
        hint = hint_for(str(exc))
        if hint:
            # A recognised code: say what actually has to change, and skip the
            # generic guesses below, which would only mislead.
            print(f"\n{hint}", file=sys.stderr)
            return EXIT_CONNECTION
        if settings.authenticator == "externalbrowser":
            print(
                "\nWith browser single sign-on this usually means:\n"
                "  - The identity provider refused the login -- your account may\n"
                "    not be connected to the Arc sandbox yet. Ask Arc to check.\n"
                "  - Sign-on was cancelled or timed out; run this again.",
                file=sys.stderr,
            )
        else:
            print(
                "\nCheck that the credential in .env is current, and that the\n"
                "account, role and warehouse are the ones Arc gave you.",
                file=sys.stderr,
            )
        _print_authenticator_help(settings)
        return EXIT_CONNECTION
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return EXIT_CONNECTION

    print("\nDone." if not mismatches else "\nDone, with warnings above.")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
