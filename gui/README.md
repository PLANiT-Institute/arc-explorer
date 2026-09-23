# Arc Explorer (PLANiT-local layer)

This directory and `arc.command` at the repository root are PLANiT's own layer
on top of the Arc sandbox template. They are excluded from
`arc-sandbox/planit-sandbox` via `.git/info/exclude`, so nothing here is pushed
to Arc.

| Path | What it is |
|------|------------|
| `../arc.command` | Double-click launcher: prepares Python, signs in, reports the session, caches the schema |
| `arc_explorer/config.py` | Every setting, loaded from `.env` |
| `arc_explorer/connection.py` | Connection and authentication to the warehouse |
| `arc_explorer/schema_cache.py` | Table/column catalogue into `data/schema_cache.json` |
| `arc_explorer/sql_guard.py` | Read-only validation for anything typed as raw SQL |
| `scripts/connect.py` | What `arc.command` runs |
| `scripts/dump_schema.py` | Schema refresh on its own |
| `data/arc-launcher.log` | Last launcher run, for support |

## Getting connected

Double-click `arc.command` in Finder, or from a terminal:

```bash
./arc.command
```

On first run it creates `.venv`, installs dependencies, and copies
`.env.example` to `.env` if you have no `.env` yet. Set `SNOWFLAKE_USER` to
your work email, then run it again.

Options: `--refresh-schema`, `--no-schema`, `--authenticator NAME`,
`--reinstall`, `--help`.

## Choosing a sign-in method

For password/MFA login, the launcher asks for username, password and a fresh
six-digit code in the terminal. Password/code input is hidden. After login,
the browser explorer reuses that connection; leave the terminal open.

## Browsing and saving data

Expand database → schema → table → columns in the left tree. Click a table
to preview it. Search values, add column conditions, choose visible columns,
or click a column header to sort; no SQL input is required.

**불러오기 · 저장** loads the current selection into a separate tab and saves
it locally under `gui/data/saved/`. Multiple saved datasets remain available
in the sidebar after restarting. Snapshots are isolated by account, user,
role and schema. They do not automatically refresh when the warehouse changes.

Loads start at the first matching row and are capped by `ARC_MAX_ROWS` (5,000
by default). The UI marks partial snapshots. Preview pages contain 100 rows;
CSV export exports the current preview page or the filtered saved snapshot.
`--no-schema` performs only the connection check without opening the explorer.

## Other authentication methods

`SNOWFLAKE_AUTHENTICATOR` in `.env` decides how you sign in. All of these are
supported; only one needs to work.

| Value | Needs | Notes |
|-------|-------|-------|
| `externalbrowser` | nothing | Browser SSO. Default. Fails if your account is not wired into Arc's identity provider. |
| `snowflake` | `SNOWFLAKE_PASSWORD` | Snowflake's own login. |
| `username_password_mfa` | `SNOWFLAKE_PASSWORD` | Adds MFA; the token is cached after the first approval. |
| `snowflake_jwt` | `SNOWFLAKE_PRIVATE_KEY_FILE` | Key pair. No browser. Snowflake's recommendation for scripts. |
| `programmatic_access_token` | `SNOWFLAKE_TOKEN` | Token issued by Snowflake. |
| `oauth` | `SNOWFLAKE_TOKEN` | OAuth access token. |
| `oauth_authorization_code` | `SNOWFLAKE_OAUTH_CLIENT_ID` | The driver opens a browser at Snowflake's own sign-in page, so a **passkey** works as the second factor. The client id comes from a security integration only an Arc account admin can create. |

To try one without editing `.env`:

```bash
./arc.command --authenticator snowflake
```

Secrets live only in `.env`, which is gitignored. They are never logged, and
they are kept out of `Settings.__repr__` so a traceback cannot print them.

### If browser SSO fails at the identity provider

The browser opens, JumpCloud rejects the login, and nothing else happens. That
means Snowflake handed off correctly but your account is not accepted by Arc's
identity provider — no local change fixes it. Either ask Arc to connect your
user to the sandbox SSO, or ask them to issue one of the alternatives above.
A key pair is the usual answer: you generate the pair, send Arc only the public
half, and point `SNOWFLAKE_PRIVATE_KEY_FILE` at the private half.

## Development

```bash
uv sync --extra dev
uv run pytest
uv run ruff check . --fix
uv run ruff format .
uv run mypy gui/arc_explorer/
```
