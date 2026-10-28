"""Read-only SQLite with execution-time authorization and bounded work."""

from contextlib import closing
from pathlib import Path
import re
import sqlite3
import time

from .errors import AgentError
from .settings import Budgets


def validate_database(path, *, protocol="v1"):
    """실행 전에 orders가 계약에 맞는 실제 테이블인지 읽기 전용으로 검사한다."""
    try:
        # mode=ro는 경로 오타로 빈 DB가 생성되는 것도 방지한다.
        with closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=0)) as db:
            if protocol == "v2":
                from .semalign import TABLES
                for table, expected in TABLES.items():
                    kind = db.execute("SELECT type FROM sqlite_master WHERE name=?", (table,)).fetchone()
                    if kind != ("table",) or {r[1] for r in db.execute(f"PRAGMA table_info({table})")} != expected:
                        raise AgentError("invalid_config")
                return
            kind = db.execute("SELECT type FROM sqlite_master WHERE name='orders'").fetchone()
            columns = [(row[1], row[2].upper()) for row in db.execute("PRAGMA table_info(orders)")]
            if kind != ("table",) or columns != [
                ("order_id", "TEXT"), ("ordered_at", "TEXT"), ("order_total_cents", "INTEGER")
            ]:
                raise AgentError("invalid_config")
    except (sqlite3.Error, OSError, ValueError):
        raise AgentError("invalid_config") from None


def _authorize(action, arg1, arg2, database, source):
    """SQLite 콜백: 허용된 테이블·열·COUNT 외의 접근을 실행 시점에 거부한다."""
    if action == sqlite3.SQLITE_SELECT:
        return sqlite3.SQLITE_OK
    # SQLite's COUNT(*) fast path reports no database for its empty-column read.
    if action == sqlite3.SQLITE_READ and (database == "main" or (database is None and arg2 == "")) and arg1 == "orders" and source is None:
        if arg2 in {"", "order_id", "ordered_at", "order_total_cents"}:
            return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_FUNCTION and arg2.lower() == "count":
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def query(path, sql, budgets: Budgets, *, deadline: float, protocol="v1", concept_id=None, parameters=None):
    """SQL의 읽기 권한·실행 비용·결과 크기를 제한하고 결과를 반환한다."""
    if time.monotonic() >= deadline:
        raise AgentError("request_timeout")
    prefix = r"\s*(?:SELECT|WITH)\b" if protocol == "v2" else r"\s*SELECT\b"
    if type(sql) is not str or len(sql) > budgets.sql_max_chars or not re.match(prefix, sql, re.I):
        raise AgentError("sql_error")
    if protocol == "v2":
        # Lex string literals separately from comments/quoted identifiers. SQLite
        # compares naive timestamp text lexically, so a UTC suffix can drop midnight rows.
        literals = re.findall(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|`(?:``|[^`])*`|\[[^\]]*\]|--[^\n]*|/\*[\s\S]*?\*/", sql)
        if any(re.fullmatch(r"'\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})'", token, re.I)
               for token in literals):
            raise AgentError("sql_error")
        if parameters is not None and (type(parameters) is not dict
                or set(parameters) != {"week_start", "week_end", "previous_start", "history_start"}
                or any(type(value) is not str or not re.fullmatch(
                    r"\d{4}-\d{2}-\d{2}T00:00:00" if key == "history_start" else r"\d{4}-\d{2}-\d{2}", value)
                       for key, value in parameters.items())):
            raise AgentError("sql_error")
    stop = min(deadline, time.monotonic() + budgets.sql_timeout_seconds)
    steps = 0
    step_interval = min(100, budgets.sql_vm_steps)

    def progress():
        """SQLite 콜백: VM 실행량 또는 시간 상한을 넘으면 쿼리를 중단한다."""
        nonlocal steps
        steps += step_interval
        return int(steps >= budgets.sql_vm_steps or time.monotonic() >= stop)

    def authorize_v2(action, arg1, arg2, database, source):
        """SQLite callback allows current-schema reads and bounded aggregate functions."""
        from .semalign import TABLES
        allowed = {"orders"}
        if concept_id in {"sa_food_orders", "sa_drink_orders"}:
            allowed |= {"order_items", "products"}
        if action == sqlite3.SQLITE_SELECT:
            return sqlite3.SQLITE_OK
        if (action == sqlite3.SQLITE_READ and database in ("main", None)
                and arg1 in allowed and arg2 in TABLES[arg1] | {""}):
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() in {"count", "sum", "avg", "min", "max", "date", "nullif", "coalesce", "abs"}:
            return sqlite3.SQLITE_OK
        # Recursive CTEs, writes, pragmas, extension functions and other DBs deny.
        return sqlite3.SQLITE_DENY

    try:
        with closing(sqlite3.connect(
            Path(path).resolve().as_uri() + "?mode=ro", uri=True,
            timeout=min(0.05, max(0, stop - time.monotonic())),
        )) as db:
            db.execute("PRAGMA query_only=ON")
            # 문자열 검사만 믿지 않고 SQLite 실행 권한과 VM 진행 콜백을 함께 제한한다.
            db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 65536)
            db.set_authorizer(authorize_v2 if protocol == "v2" else _authorize)
            db.set_progress_handler(progress, step_interval)
            executed = []
            if protocol == "v2":
                db.set_trace_callback(executed.append)
            cursor = db.execute(sql, parameters or {})
            rows = cursor.fetchmany(budgets.sql_max_rows + 1)
            if time.monotonic() >= stop or len(rows) > budgets.sql_max_rows:
                raise AgentError("sql_error")
            result = {"columns": [col[0] for col in cursor.description], "rows": rows}
            if protocol == "v2":
                if len(executed) != 1 or len(executed[0]) > budgets.sql_max_chars:
                    raise AgentError("sql_error")
                result["executed_sql"] = executed[0]
            return result
    except (sqlite3.Error, ValueError, OSError, UnicodeError):
        if time.monotonic() >= deadline:
            raise AgentError("request_timeout") from None
        raise AgentError("sql_error") from None
