"""Tests for the parts of the connection layer that need no warehouse.

Connecting itself is I/O against Snowflake and is exercised by `arc.command`.
What is tested here is the mapping from `.env` to connector arguments, and the
mismatch detection that catches a role Snowflake silently did not apply.
"""

from __future__ import annotations

import dataclasses

import pytest
from arc_explorer.config import Settings
from arc_explorer.connection import (
    APPLICATION_NAME,
    AUTHENTICATORS,
    CredentialMissing,
    SessionInfo,
    auth_params,
    connection_params,
    describe_authenticator,
    describe_mismatches,
    hint_for,
)
from arc_explorer.schema_cache import summarise_cache


def make_settings(**overrides) -> Settings:
    base: dict = {
        "user": "first.last@planit.institute",
        "account": "ACCT-123",
        "authenticator": "externalbrowser",
        "role": "PLANIT_SANDBOX_ROLE",
        "warehouse": "PLANIT_SANDBOX_WAREHOUSE",
        "database": "ARCDW_PROD",
        "schema": "DATA_EXCHANGE_LAYER",
        "max_rows": 5000,
        "default_limit": 500,
        "statement_timeout_seconds": 120,
        "host": "127.0.0.1",
        "port": 8787,
        "log_level": "INFO",
    }
    base.update(overrides)
    return Settings(**base)


def make_info(**overrides) -> SessionInfo:
    base: dict = {
        "user": "FIRST.LAST@PLANIT.INSTITUTE",
        "role": "PLANIT_SANDBOX_ROLE",
        "warehouse": "PLANIT_SANDBOX_WAREHOUSE",
        "database": "ARCDW_PROD",
        "schema": "DATA_EXCHANGE_LAYER",
        "account": "ACCT-123",
        "region": "AWS_AP_SOUTHEAST_2",
        "snowflake_version": "9.0.0",
        "table_count": 42,
        "elapsed_seconds": 1.5,
    }
    base.update(overrides)
    return SessionInfo(**base)


class TestConnectionParams:
    def test_every_coordinate_comes_from_settings(self):
        settings = make_settings(account="OTHER-ACCT", role="OTHER_ROLE")
        params = connection_params(settings)

        assert params["account"] == "OTHER-ACCT"
        assert params["role"] == "OTHER_ROLE"
        assert params["user"] == settings.user
        assert params["warehouse"] == settings.warehouse
        assert params["database"] == settings.database
        assert params["schema"] == settings.schema

    def test_statement_timeout_is_passed_as_a_session_parameter(self):
        params = connection_params(make_settings(statement_timeout_seconds=45))
        assert params["session_parameters"]["STATEMENT_TIMEOUT_IN_SECONDS"] == 45

    def test_session_is_tagged_for_query_attribution(self):
        assert connection_params(make_settings())["application"] == APPLICATION_NAME

    def test_browser_sso_sends_no_credential(self):
        params = connection_params(make_settings())
        assert params["authenticator"] == "externalbrowser"
        assert not {"password", "token", "private_key_file"} & set(params)

    def test_browser_sso_caches_its_token(self):
        # Otherwise every run re-opens the identity provider.
        assert connection_params(make_settings())["client_store_temporary_credential"]


class TestAuthenticators:
    """Each supported sign-in method, and the .env line it depends on."""

    def test_snowflake_login_uses_the_password(self):
        params = auth_params(
            make_settings(authenticator="snowflake", password="s3cret")
        )
        assert params == {"authenticator": "snowflake", "password": "s3cret"}

    def test_snowflake_login_without_a_password_names_the_variable(self):
        with pytest.raises(CredentialMissing, match="SNOWFLAKE_PASSWORD"):
            auth_params(make_settings(authenticator="snowflake"))

    def test_mfa_login_caches_its_token_and_accepts_a_passcode(self):
        params = auth_params(
            make_settings(
                authenticator="username_password_mfa",
                password="s3cret",
                passcode="123456",
            )
        )
        assert params["client_request_mfa_token"] is True
        assert params["passcode"] == "123456"

    def test_key_pair_points_at_an_existing_file(self, tmp_path):
        key = tmp_path / "arc_key.p8"
        key.write_text("-----BEGIN PRIVATE KEY-----")
        params = auth_params(
            make_settings(authenticator="snowflake_jwt", private_key_file=str(key))
        )
        assert params["private_key_file"] == str(key)
        assert "private_key_file_pwd" not in params

    def test_key_pair_passphrase_is_passed_when_set(self, tmp_path):
        key = tmp_path / "arc_key.p8"
        key.write_text("-----BEGIN ENCRYPTED PRIVATE KEY-----")
        params = auth_params(
            make_settings(
                authenticator="snowflake_jwt",
                private_key_file=str(key),
                private_key_file_pwd="phrase",
            )
        )
        assert params["private_key_file_pwd"] == "phrase"

    def test_missing_key_file_is_reported_before_the_network(self, tmp_path):
        with pytest.raises(CredentialMissing, match="does not exist"):
            auth_params(
                make_settings(
                    authenticator="snowflake_jwt",
                    private_key_file=str(tmp_path / "absent.p8"),
                )
            )

    def test_key_path_is_user_expanded(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        key = tmp_path / "arc_key.p8"
        key.write_text("-----BEGIN PRIVATE KEY-----")
        params = auth_params(
            make_settings(
                authenticator="snowflake_jwt", private_key_file="~/arc_key.p8"
            )
        )
        assert params["private_key_file"] == str(key)

    @pytest.mark.parametrize("auth", ["programmatic_access_token", "oauth"])
    def test_token_authenticators_send_the_token(self, auth):
        params = auth_params(make_settings(authenticator=auth, token="tok"))
        assert params == {"authenticator": auth, "token": "tok"}

    @pytest.mark.parametrize("auth", ["programmatic_access_token", "oauth"])
    def test_token_authenticators_name_the_missing_variable(self, auth):
        with pytest.raises(CredentialMissing, match="SNOWFLAKE_TOKEN"):
            auth_params(make_settings(authenticator=auth))

    def test_oauth_authorization_code_needs_only_a_client_id(self):
        params = auth_params(
            make_settings(
                authenticator="oauth_authorization_code", oauth_client_id="cid"
            )
        )
        assert params == {
            "authenticator": "oauth_authorization_code",
            "oauth_client_id": "cid",
        }

    def test_oauth_authorization_code_passes_optional_settings(self):
        params = auth_params(
            make_settings(
                authenticator="oauth_authorization_code",
                oauth_client_id="cid",
                oauth_client_secret="csecret",
                oauth_redirect_uri="http://127.0.0.1:8899",
            )
        )
        assert params["oauth_client_secret"] == "csecret"
        assert params["oauth_redirect_uri"] == "http://127.0.0.1:8899"

    def test_oauth_authorization_code_names_the_missing_variable(self):
        with pytest.raises(CredentialMissing, match="SNOWFLAKE_OAUTH_CLIENT_ID"):
            auth_params(make_settings(authenticator="oauth_authorization_code"))

    def test_unknown_authenticator_lists_the_supported_ones(self):
        with pytest.raises(CredentialMissing, match="not supported"):
            auth_params(make_settings(authenticator="carrier-pigeon"))

    def test_every_documented_authenticator_is_reachable(self):
        # The .env.example table and the dispatch must not drift apart.
        for auth in AUTHENTICATORS:
            described = describe_authenticator(make_settings(authenticator=auth))
            assert described.startswith(auth)

    def test_description_never_contains_a_secret(self):
        described = describe_authenticator(
            make_settings(authenticator="snowflake", password="s3cret")
        )
        assert "s3cret" not in described


class TestSecretsStayOutOfOutput:
    def test_repr_of_settings_hides_every_credential(self):
        settings = make_settings(
            password="pw-secret",
            passcode="000111",
            private_key_file_pwd="phrase-secret",
            token="token-secret",
        )
        rendered = repr(settings)
        settings = dataclasses.replace(settings, oauth_client_secret="oauth-secret")
        rendered = repr(settings)
        for secret in (
            "pw-secret",
            "000111",
            "phrase-secret",
            "token-secret",
            "oauth-secret",
        ):
            assert secret not in rendered


class TestDescribeMismatches:
    def test_matching_session_reports_nothing(self):
        settings = make_settings()
        assert describe_mismatches(make_info(), settings) == []

    def test_case_differences_are_not_mismatches(self):
        settings = make_settings(role="planit_sandbox_role")
        assert describe_mismatches(make_info(), settings) == []

    def test_silently_substituted_role_is_reported(self):
        lines = describe_mismatches(make_info(role="PUBLIC"), make_settings())
        assert len(lines) == 1
        assert "role" in lines[0]
        assert "PUBLIC" in lines[0]
        assert "PLANIT_SANDBOX_ROLE" in lines[0]

    def test_unset_warehouse_is_reported(self):
        lines = describe_mismatches(make_info(warehouse=""), make_settings())
        assert "warehouse is unset" in lines[0]

    def test_every_mismatched_field_is_listed(self):
        info = make_info(role="PUBLIC", warehouse="OTHER", schema="PUBLIC")
        assert len(describe_mismatches(info, make_settings())) == 3


class TestSummariseCache:
    def test_counts_tables_and_columns(self):
        payload = {
            "database": "ARCDW_PROD",
            "schema": "DATA_EXCHANGE_LAYER",
            "tables": [{"TABLE_NAME": "COMPANY"}, {"TABLE_NAME": "METRIC"}],
            "columns": [{"COLUMN_NAME": "ID"}],
        }
        assert summarise_cache(payload) == (
            "ARCDW_PROD.DATA_EXCHANGE_LAYER: 2 tables, 1 columns"
        )

    def test_tolerates_a_truncated_payload(self):
        assert summarise_cache({}) == "?.?: 0 tables, 0 columns"


@pytest.mark.parametrize("field", ["role", "warehouse", "database", "schema"])
def test_each_checked_field_can_trip_the_mismatch_report(field):
    lines = describe_mismatches(make_info(**{field: "SOMETHING_ELSE"}), make_settings())
    assert any(line.startswith(field) for line in lines)


class TestErrorHints:
    """Snowflake's own wording sends the reader to the wrong place."""

    def test_network_policy_error_names_the_admin_action(self):
        hint = hint_for(
            "390432 (08001): Failed to connect to DB: x.snowflakecomputing.com:443. "
            "Fail : Network policy is required."
        )
        assert hint is not None
        assert "network policy" in hint.lower()
        assert "ALTER USER" in hint

    def test_network_policy_error_does_not_blame_the_credential(self):
        # The token is valid in this case; telling the user to check it wastes
        # their time and sends them back to Arc with the wrong question.
        hint = hint_for("390432 (08001): Fail : Network policy is required.")
        assert "token is valid" in hint

    def test_oauth_rejection_points_at_the_pat_authenticator(self):
        hint = hint_for("390303 (08001): Invalid OAuth access token.")
        assert "programmatic_access_token" in hint

    def test_bad_password_mentions_sso_users_have_none(self):
        hint = hint_for("390100 (08001): Incorrect username or password was specified.")
        assert "single sign-on" in hint

    def test_unrecognised_error_gets_no_hint(self):
        assert hint_for("999999 (08001): Something entirely new.") is None

    def test_code_is_matched_even_when_not_at_the_start(self):
        assert hint_for("Error 390432 (08001): Network policy is required.") is not None
