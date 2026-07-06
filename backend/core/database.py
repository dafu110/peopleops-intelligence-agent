import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from .config import get_settings


SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL DEFAULT 'hrbp',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS interview_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    org_id TEXT NOT NULL DEFAULT 'default-org',
    department_id TEXT NOT NULL DEFAULT 'peopleops',
    candidate_name TEXT NOT NULL,
    interview_time TEXT NOT NULL,
    status TEXT NOT NULL,
    email_draft_path TEXT,
    calendar_event_path TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rag_evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    question TEXT NOT NULL,
    expected_keywords TEXT NOT NULL,
    retrieved_sources TEXT NOT NULL,
    passed INTEGER NOT NULL,
    metrics_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS approval_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    org_id TEXT NOT NULL DEFAULT 'default-org',
    department_id TEXT NOT NULL DEFAULT 'peopleops',
    action_type TEXT NOT NULL,
    subject_ref TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    approved_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_task_runs (
    task_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    org_id TEXT NOT NULL DEFAULT 'default-org',
    department_id TEXT NOT NULL DEFAULT 'peopleops',
    status TEXT NOT NULL,
    input_text TEXT NOT NULL,
    intent TEXT DEFAULT '',
    state_json TEXT NOT NULL DEFAULT '{}',
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS agent_task_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    org_id TEXT NOT NULL DEFAULT 'default-org',
    department_id TEXT NOT NULL DEFAULT 'peopleops',
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agent_task_events_task_created
ON agent_task_events (task_id, created_at);

CREATE TABLE IF NOT EXISTS tool_executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_name TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    org_id TEXT NOT NULL DEFAULT 'default-org',
    department_id TEXT NOT NULL DEFAULT 'peopleops',
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    request_json TEXT NOT NULL DEFAULT '{}',
    response_json TEXT,
    error_json TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS tool_compensations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_execution_key TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    org_id TEXT NOT NULL DEFAULT 'default-org',
    department_id TEXT NOT NULL DEFAULT 'peopleops',
    status TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    reason TEXT NOT NULL,
    response_json TEXT,
    error_json TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT
);
"""


POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL DEFAULT 'hrbp',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS interview_actions (
    id SERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    org_id TEXT NOT NULL DEFAULT 'default-org',
    department_id TEXT NOT NULL DEFAULT 'peopleops',
    candidate_name TEXT NOT NULL,
    interview_time TEXT NOT NULL,
    status TEXT NOT NULL,
    email_draft_path TEXT,
    calendar_event_path TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rag_evaluations (
    id SERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    question TEXT NOT NULL,
    expected_keywords TEXT NOT NULL,
    retrieved_sources TEXT NOT NULL,
    passed INTEGER NOT NULL,
    metrics_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS approval_requests (
    id SERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    org_id TEXT NOT NULL DEFAULT 'default-org',
    department_id TEXT NOT NULL DEFAULT 'peopleops',
    action_type TEXT NOT NULL,
    subject_ref TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    approved_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_task_runs (
    task_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    org_id TEXT NOT NULL DEFAULT 'default-org',
    department_id TEXT NOT NULL DEFAULT 'peopleops',
    status TEXT NOT NULL,
    input_text TEXT NOT NULL,
    intent TEXT DEFAULT '',
    state_json TEXT NOT NULL DEFAULT '{}',
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS agent_task_events (
    id SERIAL PRIMARY KEY,
    task_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    org_id TEXT NOT NULL DEFAULT 'default-org',
    department_id TEXT NOT NULL DEFAULT 'peopleops',
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agent_task_events_task_created
ON agent_task_events (task_id, created_at);

CREATE TABLE IF NOT EXISTS tool_executions (
    id SERIAL PRIMARY KEY,
    tool_name TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    org_id TEXT NOT NULL DEFAULT 'default-org',
    department_id TEXT NOT NULL DEFAULT 'peopleops',
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    request_json TEXT NOT NULL DEFAULT '{}',
    response_json TEXT,
    error_json TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS tool_compensations (
    id SERIAL PRIMARY KEY,
    tool_execution_key TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    org_id TEXT NOT NULL DEFAULT 'default-org',
    department_id TEXT NOT NULL DEFAULT 'peopleops',
    status TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    reason TEXT NOT NULL,
    response_json TEXT,
    error_json TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT
);
"""


class DbConn:
    def execute(self, sql: str, params: Any = ()) -> Any:
        raise NotImplementedError

    def executescript(self, script: str) -> None:
        raise NotImplementedError

    def commit(self) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


class SqliteConn(DbConn):
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def execute(self, sql: str, params: Any = ()) -> sqlite3.Cursor:
        return self.conn.execute(sql, params)

    def executescript(self, script: str) -> None:
        self.conn.executescript(script)

    def commit(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()


class ResultCursor:
    def __init__(self, rows: list[Dict[str, Any]], lastrowid: Optional[int] = None):
        self._rows = rows
        self.lastrowid = lastrowid

    def fetchall(self) -> list[Dict[str, Any]]:
        return self._rows

    def fetchone(self) -> Optional[Dict[str, Any]]:
        return self._rows[0] if self._rows else None


class PostgresConn(DbConn):
    def __init__(self, engine: Engine):
        self.connection = engine.connect()
        self.transaction = self.connection.begin()

    def execute(self, sql: str, params: Any = ()) -> ResultCursor:
        translated_sql, translated_params = _translate_sql(sql, params)
        result = self.connection.execute(text(translated_sql), translated_params)
        rows = [dict(row._mapping) for row in result.fetchall()] if result.returns_rows else []
        return ResultCursor(rows, lastrowid=_extract_lastrowid(rows))

    def executescript(self, script: str) -> None:
        for statement in [item.strip() for item in script.split(";") if item.strip()]:
            self.connection.execute(text(statement))

    def commit(self) -> None:
        self.transaction.commit()

    def close(self) -> None:
        self.connection.close()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _postgres_engine() -> Engine:
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required when DATABASE_BACKEND is not sqlite.")
    return create_engine(settings.database_url, pool_pre_ping=True)


def _is_postgres() -> bool:
    return get_settings().database_backend != "sqlite"


def _translate_sql(sql: str, params: Any) -> tuple[str, Dict[str, Any]]:
    if not isinstance(params, (list, tuple)):
        translated = _translate_postgres_statement(sql)
        return translated, params or {}

    param_map: Dict[str, Any] = {}
    translated = ""
    param_index = 0
    for char in sql:
        if char == "?":
            name = f"p{param_index}"
            translated += f":{name}"
            param_map[name] = params[param_index]
            param_index += 1
        else:
            translated += char
    translated = _translate_postgres_statement(translated)
    return translated, param_map


def _translate_postgres_statement(sql: str) -> str:
    translated = sql.replace("last_insert_rowid()", "LASTVAL()")
    if "INSERT OR IGNORE INTO users" in translated:
        translated = translated.replace("INSERT OR IGNORE INTO users", "INSERT INTO users")
        if "ON CONFLICT" not in translated:
            translated += " ON CONFLICT (username) DO NOTHING"
    elif "INSERT OR IGNORE" in translated:
        translated = translated.replace("INSERT OR IGNORE", "INSERT")

    if "INSERT OR REPLACE INTO agent_task_runs" in translated:
        translated = translated.replace("INSERT OR REPLACE INTO agent_task_runs", "INSERT INTO agent_task_runs")
        if "ON CONFLICT" not in translated:
            translated += """
            ON CONFLICT (task_id) DO UPDATE SET
                thread_id = EXCLUDED.thread_id,
                tenant_id = EXCLUDED.tenant_id,
                org_id = EXCLUDED.org_id,
                department_id = EXCLUDED.department_id,
                status = EXCLUDED.status,
                input_text = EXCLUDED.input_text,
                state_json = EXCLUDED.state_json,
                updated_at = EXCLUDED.updated_at
            """
    elif "INSERT OR REPLACE" in translated:
        translated = translated.replace("INSERT OR REPLACE", "INSERT")

    tables_with_integer_id = (
        "interview_actions",
        "rag_evaluations",
        "approval_requests",
        "tool_executions",
        "tool_compensations",
        "agent_task_events",
    )
    if (
        "INSERT INTO" in translated
        and "RETURNING id" not in translated
        and any(f"INSERT INTO {table}" in translated for table in tables_with_integer_id)
    ):
        translated += " RETURNING id"
    return translated


def _extract_lastrowid(rows: list[Dict[str, Any]]) -> Optional[int]:
    if not rows:
        return None
    value = rows[0].get("id")
    return int(value) if value is not None else None


def init_db() -> None:
    settings = get_settings()
    if _is_postgres():
        conn: DbConn = PostgresConn(_postgres_engine())
    else:
        settings.db_path.parent.mkdir(parents=True, exist_ok=True)
        raw_conn = sqlite3.connect(settings.db_path)
        raw_conn.row_factory = sqlite3.Row
        conn = SqliteConn(raw_conn)
    try:
        conn.executescript(POSTGRES_SCHEMA if _is_postgres() else SQLITE_SCHEMA)
        if not _is_postgres():
            _ensure_columns(conn)
        conn.execute(
            """
            INSERT OR IGNORE INTO users (username, role, created_at)
            VALUES (?, ?, ?)
            """,
            ("local-admin", "admin", utc_now()),
        )
        conn.commit()
    finally:
        conn.close()


def _ensure_columns(conn: DbConn) -> None:
    existing_interview_columns = {row[1] for row in conn.execute("PRAGMA table_info(interview_actions)").fetchall()}
    for column, definition in {
        "tenant_id": "TEXT NOT NULL DEFAULT 'default'",
        "org_id": "TEXT NOT NULL DEFAULT 'default-org'",
        "department_id": "TEXT NOT NULL DEFAULT 'peopleops'",
    }.items():
        if column not in existing_interview_columns:
            conn.execute(f"ALTER TABLE interview_actions ADD COLUMN {column} {definition}")

    existing_rag_columns = {row[1] for row in conn.execute("PRAGMA table_info(rag_evaluations)").fetchall()}
    if "tenant_id" not in existing_rag_columns:
        conn.execute("ALTER TABLE rag_evaluations ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'default'")
    if "metrics_json" not in existing_rag_columns:
        conn.execute("ALTER TABLE rag_evaluations ADD COLUMN metrics_json TEXT DEFAULT '{}'")

    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_tool_executions_idempotency
        ON tool_executions (idempotency_key)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_agent_task_events_task_created
        ON agent_task_events (task_id, created_at)
        """
    )


@contextmanager
def get_conn() -> Iterator[DbConn]:
    init_db()
    settings = get_settings()
    if _is_postgres():
        conn: DbConn = PostgresConn(_postgres_engine())
    else:
        raw_conn = sqlite3.connect(settings.db_path)
        raw_conn.row_factory = sqlite3.Row
        conn = SqliteConn(raw_conn)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def create_interview_action(
    *,
    tenant_id: str = "default",
    org_id: str = "default-org",
    department_id: str = "peopleops",
    candidate_name: str,
    interview_time: str,
    status: str,
    email_draft_path: Optional[Path],
    calendar_event_path: Optional[Path],
    created_by: str,
) -> int:
    with get_conn() as conn:
        cursor = conn.execute(
            """
            INSERT INTO interview_actions (
                tenant_id,
                org_id,
                department_id,
                candidate_name,
                interview_time,
                status,
                email_draft_path,
                calendar_event_path,
                created_by,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tenant_id,
                org_id,
                department_id,
                candidate_name,
                interview_time,
                status,
                str(email_draft_path) if email_draft_path else None,
                str(calendar_event_path) if calendar_event_path else None,
                created_by,
                utc_now(),
            ),
        )
        return int(cursor.lastrowid)


def list_interview_actions(limit: int = 20, *, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        params: list[Any] = []
        tenant_clause = ""
        if tenant_id:
            tenant_clause = "WHERE tenant_id = ?"
            params.append(tenant_id)
        params.append(limit)
        rows = conn.execute(
            f"""
            SELECT *
            FROM interview_actions
            {tenant_clause}
            ORDER BY id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def get_interview_action(action_id: int, *, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        params: list[Any] = [action_id]
        tenant_clause = ""
        if tenant_id:
            tenant_clause = "AND tenant_id = ?"
            params.append(tenant_id)
        row = conn.execute(
            f"""
            SELECT *
            FROM interview_actions
            WHERE id = ?
            {tenant_clause}
            """,
            params,
        ).fetchone()
    return dict(row) if row else None


def update_interview_action_status(
    action_id: int,
    *,
    tenant_id: str,
    status: str,
) -> Dict[str, Any]:
    current = get_interview_action(action_id, tenant_id=tenant_id)
    if current is None:
        raise KeyError(f"Interview action not found: {action_id}")

    with get_conn() as conn:
        conn.execute(
            """
            UPDATE interview_actions
            SET status = ?
            WHERE id = ? AND tenant_id = ?
            """,
            (status, action_id, tenant_id),
        )
    updated = get_interview_action(action_id, tenant_id=tenant_id)
    if updated is None:
        raise KeyError(f"Interview action not found after update: {action_id}")
    return updated


def create_rag_evaluation(
    *,
    tenant_id: str = "default",
    question: str,
    expected_keywords: str,
    retrieved_sources: str,
    passed: bool,
    metrics: Optional[Dict[str, Any]] = None,
) -> int:
    with get_conn() as conn:
        cursor = conn.execute(
            """
            INSERT INTO rag_evaluations (
                tenant_id,
                question,
                expected_keywords,
                retrieved_sources,
                passed,
                metrics_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (tenant_id, question, expected_keywords, retrieved_sources, int(passed), json_dumps(metrics or {}), utc_now()),
        )
        return int(cursor.lastrowid)


def json_dumps(value: Dict[str, Any]) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def json_loads(value: Optional[str]) -> Dict[str, Any]:
    import json

    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def create_agent_task_run(
    *,
    task_id: str,
    thread_id: str,
    tenant_id: str = "default",
    org_id: str = "default-org",
    department_id: str = "peopleops",
    input_text: str,
    state: Optional[Dict[str, Any]] = None,
) -> str:
    timestamp = utc_now()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO agent_task_runs (
                task_id,
                thread_id,
                tenant_id,
                org_id,
                department_id,
                status,
                input_text,
                state_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                thread_id,
                tenant_id,
                org_id,
                department_id,
                "RUNNING",
                input_text,
                json_dumps(state or {}),
                timestamp,
                timestamp,
            ),
        )
    return task_id


def create_agent_task_event(
    *,
    task_id: str,
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
    tenant_id: str = "default",
    org_id: str = "default-org",
    department_id: str = "peopleops",
) -> int:
    with get_conn() as conn:
        cursor = conn.execute(
            """
            INSERT INTO agent_task_events (
                task_id,
                tenant_id,
                org_id,
                department_id,
                event_type,
                payload_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                tenant_id,
                org_id,
                department_id,
                event_type,
                json_dumps(payload or {}),
                utc_now(),
            ),
        )
        return int(cursor.lastrowid)


def update_agent_task_run(
    task_id: str,
    *,
    status: str,
    intent: str = "",
    state: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    completed_at = utc_now() if status in {"SUCCEEDED", "FAILED"} else None
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE agent_task_runs
            SET status = ?,
                intent = COALESCE(NULLIF(?, ''), intent),
                state_json = COALESCE(?, state_json),
                error = ?,
                updated_at = ?,
                completed_at = COALESCE(?, completed_at)
            WHERE task_id = ?
            """,
            (
                status,
                intent,
                json_dumps(state) if state is not None else None,
                error,
                utc_now(),
                completed_at,
                task_id,
            ),
        )
    run = get_agent_task_run(task_id)
    if run is None:
        raise KeyError(f"Agent task run not found: {task_id}")
    return run


def get_agent_task_run(task_id: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM agent_task_runs WHERE task_id = ?", (task_id,)).fetchone()
    return _decode_task_run(dict(row)) if row else None


def _decode_task_run(row: Dict[str, Any]) -> Dict[str, Any]:
    row["state"] = json_loads(row.get("state_json"))
    return row


def _decode_task_event(row: Dict[str, Any]) -> Dict[str, Any]:
    row["payload"] = json_loads(row.get("payload_json"))
    return row


def list_agent_task_events(
    task_id: str,
    *,
    tenant_id: Optional[str] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        params: list[Any] = [task_id]
        tenant_clause = ""
        if tenant_id:
            tenant_clause = "AND tenant_id = ?"
            params.append(tenant_id)
        params.append(limit)
        rows = conn.execute(
            f"""
            SELECT *
            FROM agent_task_events
            WHERE task_id = ?
            {tenant_clause}
            ORDER BY id ASC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [_decode_task_event(dict(row)) for row in rows]


def list_agent_task_runs(limit: int = 20, *, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        params: list[Any] = []
        tenant_clause = ""
        if tenant_id:
            tenant_clause = "WHERE tenant_id = ?"
            params.append(tenant_id)
        params.append(limit)
        rows = conn.execute(
            f"""
            SELECT *
            FROM agent_task_runs
            {tenant_clause}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [_decode_task_run(dict(row)) for row in rows]


def claim_tool_execution(
    *,
    tool_name: str,
    idempotency_key: str,
    tenant_id: str,
    org_id: str,
    department_id: str,
    request: Dict[str, Any],
) -> tuple[Dict[str, Any], bool]:
    timestamp = utc_now()
    try:
        with get_conn() as conn:
            existing = conn.execute(
                "SELECT * FROM tool_executions WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if existing is not None:
                return dict(existing), False
            cursor = conn.execute(
                """
                INSERT INTO tool_executions (
                    tool_name,
                    idempotency_key,
                    tenant_id,
                    org_id,
                    department_id,
                    status,
                    attempts,
                    request_json,
                    started_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tool_name,
                    idempotency_key,
                    tenant_id,
                    org_id,
                    department_id,
                    "RUNNING",
                    0,
                    json_dumps(request),
                    timestamp,
                ),
            )
            row_id = int(cursor.lastrowid)
            row = conn.execute("SELECT * FROM tool_executions WHERE id = ?", (row_id,)).fetchone()
            return dict(row), True
    except (sqlite3.IntegrityError, IntegrityError):
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM tool_executions WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if row is None:
                raise
            return dict(row), False


def update_tool_execution(
    *,
    idempotency_key: str,
    status: str,
    attempts: int,
    response: Optional[Dict[str, Any]] = None,
    error: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    completed_at = utc_now() if status in {"SUCCEEDED", "FAILED"} else None
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE tool_executions
            SET status = ?,
                attempts = ?,
                response_json = ?,
                error_json = ?,
                completed_at = COALESCE(?, completed_at)
            WHERE idempotency_key = ?
            """,
            (
                status,
                attempts,
                json_dumps(response) if response is not None else None,
                json_dumps(error) if error is not None else None,
                completed_at,
                idempotency_key,
            ),
        )
        row = conn.execute(
            "SELECT * FROM tool_executions WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
    if row is None:
        raise KeyError(f"Tool execution not found: {idempotency_key}")
    return dict(row)


def get_tool_execution_by_key(idempotency_key: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM tool_executions WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
    return dict(row) if row else None


def list_tool_executions(limit: int = 20, *, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        params: list[Any] = []
        tenant_clause = ""
        if tenant_id:
            tenant_clause = "WHERE tenant_id = ?"
            params.append(tenant_id)
        params.append(limit)
        rows = conn.execute(
            f"""
            SELECT *
            FROM tool_executions
            {tenant_clause}
            ORDER BY id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def create_tool_compensation(
    *,
    tool_execution_key: str,
    tool_name: str,
    tenant_id: str,
    org_id: str,
    department_id: str,
    requested_by: str,
    reason: str,
) -> int:
    with get_conn() as conn:
        cursor = conn.execute(
            """
            INSERT INTO tool_compensations (
                tool_execution_key,
                tool_name,
                tenant_id,
                org_id,
                department_id,
                status,
                requested_by,
                reason,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tool_execution_key,
                tool_name,
                tenant_id,
                org_id,
                department_id,
                "RUNNING",
                requested_by,
                reason,
                utc_now(),
            ),
        )
        return int(cursor.lastrowid)


def update_tool_compensation(
    compensation_id: int,
    *,
    status: str,
    response: Optional[Dict[str, Any]] = None,
    error: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    completed_at = utc_now() if status in {"SUCCEEDED", "FAILED"} else None
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE tool_compensations
            SET status = ?,
                response_json = ?,
                error_json = ?,
                completed_at = COALESCE(?, completed_at)
            WHERE id = ?
            """,
            (
                status,
                json_dumps(response) if response is not None else None,
                json_dumps(error) if error is not None else None,
                completed_at,
                compensation_id,
            ),
        )
        row = conn.execute("SELECT * FROM tool_compensations WHERE id = ?", (compensation_id,)).fetchone()
    if row is None:
        raise KeyError(f"Tool compensation not found: {compensation_id}")
    return dict(row)


def list_tool_compensations(limit: int = 20, *, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        params: list[Any] = []
        tenant_clause = ""
        if tenant_id:
            tenant_clause = "WHERE tenant_id = ?"
            params.append(tenant_id)
        params.append(limit)
        rows = conn.execute(
            f"""
            SELECT *
            FROM tool_compensations
            {tenant_clause}
            ORDER BY id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def create_approval_request(
    *,
    tenant_id: str,
    org_id: str,
    department_id: str,
    action_type: str,
    subject_ref: str,
    payload: Dict[str, Any],
    requested_by: str,
    status: str = "PENDING",
) -> int:
    timestamp = utc_now()
    with get_conn() as conn:
        cursor = conn.execute(
            """
            INSERT INTO approval_requests (
                tenant_id,
                org_id,
                department_id,
                action_type,
                subject_ref,
                status,
                payload_json,
                requested_by,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tenant_id,
                org_id,
                department_id,
                action_type,
                subject_ref,
                status,
                json_dumps(payload),
                requested_by,
                timestamp,
                timestamp,
            ),
        )
        return int(cursor.lastrowid)


def list_approval_requests(limit: int = 20, *, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        params: list[Any] = []
        tenant_clause = ""
        if tenant_id:
            tenant_clause = "WHERE tenant_id = ?"
            params.append(tenant_id)
        params.append(limit)
        rows = conn.execute(
            f"""
            SELECT *
            FROM approval_requests
            {tenant_clause}
            ORDER BY id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def get_approval_request(approval_id: int, *, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        params: list[Any] = [approval_id]
        tenant_clause = ""
        if tenant_id:
            tenant_clause = "AND tenant_id = ?"
            params.append(tenant_id)
        row = conn.execute(
            f"""
            SELECT *
            FROM approval_requests
            WHERE id = ?
            {tenant_clause}
            """,
            params,
        ).fetchone()
    return dict(row) if row else None


APPROVAL_TRANSITIONS = {
    "PENDING": {"APPROVED", "REJECTED"},
    "APPROVED": {"EXECUTED", "FAILED"},
    "REJECTED": set(),
    "EXECUTED": set(),
    "FAILED": set(),
}


def update_approval_status(
    approval_id: int,
    *,
    tenant_id: str,
    status: str,
    approved_by: Optional[str] = None,
) -> Dict[str, Any]:
    current = get_approval_request(approval_id, tenant_id=tenant_id)
    if current is None:
        raise KeyError(f"Approval request not found: {approval_id}")

    next_status = status.upper()
    current_status = str(current["status"]).upper()
    if next_status not in APPROVAL_TRANSITIONS.get(current_status, set()):
        raise ValueError(f"Invalid approval transition: {current_status} -> {next_status}")

    with get_conn() as conn:
        conn.execute(
            """
            UPDATE approval_requests
            SET status = ?, approved_by = COALESCE(?, approved_by), updated_at = ?
            WHERE id = ? AND tenant_id = ?
            """,
            (next_status, approved_by, utc_now(), approval_id, tenant_id),
        )
    updated = get_approval_request(approval_id, tenant_id=tenant_id)
    if updated is None:
        raise KeyError(f"Approval request not found after update: {approval_id}")
    return updated
