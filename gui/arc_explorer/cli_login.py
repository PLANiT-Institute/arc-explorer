"""Terminal credentials, matching the successful password/MFA test."""
import dataclasses
from getpass import getpass

from arc_explorer.config import Settings


class LoginCancelled(Exception):
    """Login cancelled."""

def cli_login(settings: Settings) -> Settings:
    """Read fresh credentials without displaying password or MFA code."""
    try:
        user = input(f"Snowflake username [{settings.user}]: ").strip() or settings.user
        password = getpass("Snowflake password: ")
        passcode = getpass("Current 6-digit MFA code: ").strip()
    except (EOFError, KeyboardInterrupt) as exc:
        raise LoginCancelled() from exc
    if not password:
        raise ValueError("Password is required")
    if len(passcode) != 6 or not passcode.isascii() or not passcode.isdigit():
        raise ValueError("Current 6-digit MFA code is required")
    return dataclasses.replace(settings, user=user, password=password,
        passcode=passcode, authenticator="username_password_mfa")
