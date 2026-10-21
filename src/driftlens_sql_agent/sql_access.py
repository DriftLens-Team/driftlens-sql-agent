"""Read-only SQLite with execution-time authorization and bounded work."""

from contextlib import closing
from pathlib import Path
import re
import sqlite3
import time

from .errors import AgentError
from .settings import Budgets


def _connect(path, timeout):
    return sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=max(0, timeout))


def validate_database(path):
    try:
        with closing(_connect(path, 0)) as db:
            kind = db.execute("SELECT type FROM sqlite_master WHERE name='orders'").fetchone()
            columns = [(row[1], row[2].upper()) for row in db.execute("PRAGMA table_info(orders)")]
            if kind != ("table",) or columns != [
                ("order_id", "TEXT"), ("ordered_at", "TEXT"), ("order_total_cents", "INTEGER")
            ]:
                raise AgentError("invalid_config")
    except (sqlite3.Error, OSError, ValueError):
        raise AgentError("invalid_config") from None


def _authorize(action, arg1, arg2, database, source):
    if action == sqlite3.SQLITE_SELECT:
        return sqlite3.SQLITE_OK
    # SQLite's COUNT(*) fast path reports no database for its empty-column read.
    if action == sqlite3.SQLITE_READ and (database == "main" or (database is None and arg2 == "")) and arg1 == "orders" and source is None:
        if arg2 in {"", "order_id", "ordered_at", "order_total_cents"}:
            return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_FUNCTION and arg2.lower() == "count":
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def query(path, sql, budgets: Budgets, *, deadline: float):
    if time.monotonic() >= deadline:
        raise AgentError("request_timeout")
    if type(sql) is not str or len(sql) > budgets.sql_max_chars or not re.match(r"\s*SELECT\b", sql, re.I):
        raise AgentError("sql_error")
    stop = min(deadline, time.monotonic() + budgets.sql_timeout_seconds)
    steps = 0
    step_interval = min(100, budgets.sql_vm_steps)

    def progress():
        nonlocal steps
        steps += step_interval
        return int(steps >= budgets.sql_vm_steps or time.monotonic() >= stop)

    try:
        with closing(_connect(path, min(0.05, max(0, stop - time.monotonic())))) as db:
            db.execute("PRAGMA query_only=ON")
            db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 65536)
            db.set_authorizer(_authorize)
            db.set_progress_handler(progress, step_interval)
            cursor = db.execute(sql)
            rows = cursor.fetchmany(budgets.sql_max_rows + 1)
            if time.monotonic() >= stop or len(rows) > budgets.sql_max_rows:
                raise AgentError("sql_error")
            return {"columns": [col[0] for col in cursor.description], "rows": rows}
    except (sqlite3.Error, ValueError, OSError, UnicodeError):
        if time.monotonic() >= deadline:
            raise AgentError("request_timeout") from None
        raise AgentError("sql_error") from None
