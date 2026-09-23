"""Regression checks for fresh GUI credentials reaching Snowflake."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from arc_explorer.login import LoginCancelled, _prompt, gui_login
from arc_explorer.connection import connection_params
from test_connection import make_settings


def test_gui_credentials_override_stale_configuration():
    settings = make_settings(authenticator="snowflake", password="old-password", passcode="999999")
    with patch("arc_explorer.login._prompt", side_effect=["person@example.com", "fresh-password", "012345"]):
        result = gui_login(settings)
    params = connection_params(result)
    assert params["authenticator"] == "username_password_mfa"
    assert params["user"] == "person@example.com"
    assert params["password"] == "fresh-password"
    assert params["passcode"] == "012345"
    assert settings.password == "old-password"


@pytest.mark.parametrize("code", ["", "12345", "abcdef", "1234567"])
def test_missing_or_invalid_totp_stops_login(code):
    with patch("arc_explorer.login._prompt", side_effect=["person@example.com", "password", code]):
        with pytest.raises(ValueError, match="6-digit"):
            gui_login(make_settings())


def test_dialog_cancellation_is_handled():
    with patch("arc_explorer.login.subprocess.run", return_value=SimpleNamespace(returncode=1, stderr="User canceled. (-128)", stdout="")):
        with pytest.raises(LoginCancelled):
            _prompt("Password", hidden=True)


def test_secret_answer_is_captured_and_not_stripped():
    with patch("arc_explorer.login.subprocess.run", return_value=SimpleNamespace(returncode=0, stdout=" password \n", stderr="")) as run:
        assert _prompt("Password", hidden=True) == " password "
    assert run.call_args.kwargs["capture_output"] is True
    assert " password " not in str(run.call_args)
