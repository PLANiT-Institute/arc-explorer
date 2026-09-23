"""Read-only SQL validation and row-limit injection.

The sandbox role should already be read-only, but the GUI must not rely on that:
anything typed into the raw-SQL tab passes through here first.

Validation works on a *scrubbed* copy of the statement in which comments,
string literals, quoted identifiers and dollar-quoted blocks are replaced by
spaces. Scrubbing before matching is what stops `'; DROP TABLE x --'` inside a
literal from tripping the guard, and equally stops a comment from hiding a
second statement.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Statement kinds the GUI is willing to execute at all.
ALLOWED_LEADING_KEYWORDS = frozenset({"SELECT", "WITH"})

# Keywords that may never appear anywhere in a statement, scrubbed of strings
# and comments. Deliberately excludes GET/PUT (also Snowflake functions) and
# USE/SET, which the single-statement + leading-keyword rules already block.
FORBIDDEN_KEYWORDS = frozenset(
    {
        "INSERT",
        "UPDATE",
        "DELETE",
        "MERGE",
        "UPSERT",
        "CREATE",
        "DROP",
        "UNDROP",
        "ALTER",
        "TRUNCATE",
        "RENAME",
        "GRANT",
        "REVOKE",
        "COPY",
        "UNLOAD",
        "REMOVE",
        "CALL",
        "EXECUTE",
    }
)

_WORD = re.compile(r"[A-Za-z_][A-Za-z_0-9$]*")


class SqlNotAllowed(ValueError):
    """Raised when a statement fails read-only validation."""


@dataclass(frozen=True)
class GuardedSql:
    """A statement that passed validation, plus how it was bounded."""

    sql: str
    scrubbed: str
    limit_applied: int | None
    had_own_limit: bool


def scrub(sql: str) -> str:
    """Replace comments and quoted text with spaces, preserving character offsets.

    Preserving offsets means positions in the scrubbed string still line up with
    the original, so paren depth and keyword positions remain meaningful.
    """
    out = list(sql)
    i = 0
    n = len(sql)

    def blank(start: int, end: int) -> None:
        for k in range(start, min(end, n)):
            if out[k] != "\n":
                out[k] = " "

    while i < n:
        ch = sql[i]
        two = sql[i : i + 2]

        if two == "--":
            end = sql.find("\n", i)
            end = n if end == -1 else end
            blank(i, end)
            i = end
        elif two == "/*":
            # Snowflake block comments do not nest.
            end = sql.find("*/", i + 2)
            end = n if end == -1 else end + 2
            blank(i, end)
            i = end
        elif two == "$$":
            end = sql.find("$$", i + 2)
            end = n if end == -1 else end + 2
            blank(i, end)
            i = end
        elif ch == "'":
            j = i + 1
            while j < n:
                if sql[j] == "\\" and j + 1 < n:
                    j += 2
                    continue
                if sql[j] == "'":
                    if sql[j : j + 2] == "''":  # escaped quote
                        j += 2
                        continue
                    j += 1
                    break
                j += 1
            blank(i, j)
            i = j
        elif ch == '"':
            j = sql.find('"', i + 1)
            j = n if j == -1 else j + 1
            blank(i, j)
            i = j
        else:
            i += 1

    return "".join(out)


def _depth_zero_words(scrubbed: str) -> list[tuple[int, str]]:
    """Yield (position, UPPERCASED word) for every word outside parentheses."""
    depth = 0
    words: list[tuple[int, str]] = []
    i = 0
    n = len(scrubbed)

    while i < n:
        ch = scrubbed[i]
        if ch == "(":
            depth += 1
            i += 1
        elif ch == ")":
            depth = max(0, depth - 1)
            i += 1
        else:
            match = _WORD.match(scrubbed, i)
            if match:
                if depth == 0:
                    words.append((match.start(), match.group(0).upper()))
                i = match.end()
            else:
                i += 1

    return words


def guard(sql: str, *, default_limit: int, max_rows: int) -> GuardedSql:
    """Validate a statement as read-only and bound the rows it can return.

    Args:
        sql: Raw statement text as typed by the user.
        default_limit: Row limit appended when the statement has none of its own.
        max_rows: Hard ceiling; a caller-supplied limit above this is narrowed.

    Returns:
        The guarded statement, ready to execute.

    Raises:
        SqlNotAllowed: The statement is empty, is more than one statement, does
            not begin with SELECT or WITH, or contains a forbidden keyword.
    """
    stripped = sql.strip().rstrip(";").strip()
    if not stripped:
        raise SqlNotAllowed("Statement is empty.")

    scrubbed = scrub(stripped)

    if ";" in scrubbed:
        raise SqlNotAllowed(
            "Only one statement can be run at a time; remove the ';' and "
            "anything after it."
        )

    words = _depth_zero_words(scrubbed)
    if not words:
        raise SqlNotAllowed("No SQL keywords found outside of comments or strings.")

    leading = words[0][1]
    if leading not in ALLOWED_LEADING_KEYWORDS:
        raise SqlNotAllowed(
            f"Only read queries are allowed here: a statement must start with "
            f"SELECT or WITH, not {leading}."
        )

    # Forbidden keywords are checked at every depth, not just depth zero.
    all_words = {m.group(0).upper() for m in _WORD.finditer(scrubbed)}
    banned = sorted(all_words & FORBIDDEN_KEYWORDS)
    if banned:
        raise SqlNotAllowed(
            f"This statement is not read-only: it contains {', '.join(banned)}."
        )

    had_own_limit = any(word in {"LIMIT", "FETCH"} for _, word in words)

    limit = min(default_limit, max_rows)
    final = stripped if had_own_limit else f"{stripped}\nLIMIT {limit}"

    return GuardedSql(
        sql=final,
        scrubbed=scrubbed,
        limit_applied=None if had_own_limit else limit,
        had_own_limit=had_own_limit,
    )
