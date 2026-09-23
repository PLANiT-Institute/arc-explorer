"""Native macOS credential dialogs for the Finder launcher."""

from __future__ import annotations

import dataclasses
import subprocess

from arc_explorer.config import Settings


class LoginCancelled(Exception):
    """The user cancelled sign-in."""


def _prompt(label: str, *, hidden: bool = False, default: str = "") -> str:
    # Only non-secret UI text is passed as arguments. Answers are captured in
    # memory, never inherited by the launcher's tee/log output.
    script = '''on run argv
tell application "System Events"
activate
set answer to display dialog (item 1 of argv) with title "Transition Arc — Sign in" default answer (item 2 of argv) with hidden answer (item 3 of argv is "true") buttons {"Cancel", "Continue"} default button "Continue" cancel button "Cancel"
return text returned of answer
end tell
end run
'''
    result = subprocess.run(
        ["/usr/bin/osascript", "-", label, default, str(hidden).lower()],
        input=script, text=True, capture_output=True, check=False,
    )
    if result.returncode:
        if "-128" in result.stderr:
            raise LoginCancelled()
        raise RuntimeError("Could not open the macOS sign-in dialog. Please relaunch arc.command.")
    return result.stdout.rstrip("\r\n")


def gui_login(settings: Settings) -> Settings:
    """Collect fresh credentials and the required TOTP before connecting."""
    user = _prompt("Snowflake username", default=settings.user).strip()
    if not user:
        raise ValueError("A Snowflake username is required.")
    password = _prompt("Snowflake password", hidden=True)
    if not password:
        raise ValueError("A Snowflake password is required.")
    passcode = _prompt("Enter the current 6-digit code from your authenticator app", hidden=True).strip()
    if len(passcode) != 6 or not passcode.isascii() or not passcode.isdigit():
        raise ValueError("Enter the current 6-digit MFA code and try again.")
    return dataclasses.replace(
        settings, user=user, password=password, passcode=passcode,
        authenticator="username_password_mfa",
    )
