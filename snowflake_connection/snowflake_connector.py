# python_snowflake_connection.py

from __future__ import annotations

import os
import snowflake.connector

# Cached connection
_python_connector_conn = None
org = 'PLANIT'

def _get_python_connector(email_address: str = None):
    """
    Returns a cached Snowflake connection, creating one if needed.
    Switches connections when moving between Sandbox and RARC.
    """

    global _python_connector_conn


    # Reuse existing connection if it matches the requested type
    if (_python_connector_conn is not None):
        return _python_connector_conn

    # Close existing connection if switching environments
    if _python_connector_conn is not None:
        try:
            _python_connector_conn.close()
        except Exception:
            pass

        _python_connector_conn = None

    # Validate environment variables

    if email_address is None:
        raise RuntimeError(
            "Please insert your email address in the run_query() function call")

    _python_connector_conn = snowflake.connector.connect(
            user=email_address,
            authenticator="externalbrowser",
            account="SAAKLZV-XM04427",
            role= f"{org}_SANDBOX_ROLE",
            warehouse= f"{org}_SANDBOX_WAREHOUSE",
            database="ARCDW_PROD")

    return _python_connector_conn


def run_query(sql: str, email_address: str):
    """
    Execute a query and return a pandas DataFrame.

    Examples:
        df = run_query("SELECT * FROM MY_TABLE")

        df = run_query(
            "SELECT * FROM ARC_METRIC.METRICS",
            email_address="first.last@org.com"
        )
    """

    conn = _get_python_connector(email_address)
    cur = conn.cursor()

    try:
        cur.execute(sql)
        return cur.fetch_pandas_all()

    finally:
        cur.close()


def close_connection():
    """
    Close cached connection.
    """

    global _python_connector_conn

    if _python_connector_conn is not None:
        try:
            _python_connector_conn.close()
        except Exception:
            pass

    _python_connector_conn = None

