"""Interactive Snowflake MFA check. Credentials stay in process memory."""
from getpass import getpass
import json
from pathlib import Path

import snowflake.connector

RESULT = Path(__file__).with_name("password_mfa_result.json")


def main() -> None:
    RESULT.write_text(json.dumps({"status": "awaiting_local_input"}))
    print("Snowflake native password / MFA test")
    print("Account: SAAKLZV-XM04427 | User: sanghyun@planit.institute")
    print("Enter your Snowflake password here, not in chat. Input is hidden.")
    print("Credentials will not be saved. Ctrl+C cancels.\n")
    conn = None
    try:
        password = getpass("Snowflake password: ")
        if not password:
            raise ValueError("No password supplied")
        passcode = getpass("Authenticator code (Enter for configured push MFA): ")
        options = {"passcode": passcode} if passcode else {}
        RESULT.write_text(json.dumps({"status": "connecting"}))
        print("Connecting. Approve MFA on your device if prompted.", flush=True)
        conn = snowflake.connector.connect(
            user="sanghyun@planit.institute",
            account="SAAKLZV-XM04427",
            authenticator="username_password_mfa",
            password=password,
            role="PLANIT_SANDBOX_ROLE",
            warehouse="PLANIT_SANDBOX_WAREHOUSE",
            database="ARCDW_PROD",
            login_timeout=120,
            network_timeout=30,
            client_request_mfa_token=False,
            session_parameters={"STATEMENT_TIMEOUT_IN_SECONDS": 30},
            **options,
        )
        password = passcode = ""
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1, CURRENT_ROLE(), CURRENT_WAREHOUSE()")
            row = cursor.fetchone()
            if not row or row[0] != 1:
                raise RuntimeError("Connection check returned an unexpected result")
        result = {"status": "success", "role": row[1], "warehouse": row[2]}
        print("SUCCESS: connected and ran SELECT 1.")
    except KeyboardInterrupt:
        result = {"status": "cancelled"}
        print("\nCancelled.")
    except Exception as exc:
        result = {"status": "failed", "error_type": type(exc).__name__,
                  "error_code": getattr(exc, "errno", None),
                  "sqlstate": getattr(exc, "sqlstate", None)}
        print(f"Connection failed ({result['error_type']}, code {result['error_code']}).")
        print("The account may require a native Snowflake password or a different MFA method.")
    finally:
        if conn is not None:
            conn.close()
    RESULT.write_text(json.dumps(result, indent=2))
    input("\nPress Enter to close this test.")


if __name__ == "__main__":
    main()
