"""PostgreSQL data access helpers for the ITQAN Audit Server.

This module intentionally uses raw SQL through psycopg.
No ORM is used.
"""

from __future__ import annotations

import time
from typing import Any

import psycopg
from psycopg.rows import dict_row


REPORT_FIELDS: tuple[str, ...] = (
    "device_id",
    "rep_name",
    "app_version",
    "timestamp_ms",
    "service_running",
    "consent_accepted",
    "permissions_ok",
    "accessibility_enabled",
    "all_files_access",
    "google_account_connected",
    "drive_folder_configured",
    "sheet_configured",
    "last_call_start_ms",
    "last_call_direction",
    "last_call_duration_seconds",
    "pending_uploads",
    "total_uploaded",
    "last_upload_ms",
    "last_sync_ms",
    "notes",
)

BOOLEAN_FIELDS: tuple[str, ...] = (
    "service_running",
    "consent_accepted",
    "permissions_ok",
    "accessibility_enabled",
    "all_files_access",
    "google_account_connected",
    "drive_folder_configured",
    "sheet_configured",
)


CREATE_REPORTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS status_reports (
    id BIGSERIAL PRIMARY KEY,
    received_at_ms BIGINT NOT NULL,
    device_id TEXT NOT NULL,
    rep_name TEXT,
    app_version TEXT,
    timestamp_ms BIGINT NOT NULL,
    service_running BOOLEAN,
    consent_accepted BOOLEAN,
    permissions_ok BOOLEAN,
    accessibility_enabled BOOLEAN,
    all_files_access BOOLEAN,
    google_account_connected BOOLEAN,
    drive_folder_configured BOOLEAN,
    sheet_configured BOOLEAN,
    last_call_start_ms BIGINT,
    last_call_direction TEXT,
    last_call_duration_seconds INTEGER,
    pending_uploads INTEGER,
    total_uploaded INTEGER,
    last_upload_ms BIGINT,
    last_sync_ms BIGINT,
    notes TEXT
);
"""

CREATE_INDEXES_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_status_reports_rep_name ON status_reports(rep_name);",
    "CREATE INDEX IF NOT EXISTS idx_status_reports_timestamp_ms ON status_reports(timestamp_ms DESC);",
    "CREATE INDEX IF NOT EXISTS idx_status_reports_device_id ON status_reports(device_id);",
    "CREATE INDEX IF NOT EXISTS idx_status_reports_rep_key ON status_reports((COALESCE(NULLIF(TRIM(rep_name), ''), device_id)));",
)


def get_connection(database_url: str) -> psycopg.Connection[Any]:
    """Return a PostgreSQL connection configured for dict-like rows."""
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured.")

    return psycopg.connect(database_url, row_factory=dict_row)


def init_db(database_url: str) -> None:
    """Create the reports table and indexes if they do not already exist."""
    with get_connection(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_REPORTS_TABLE_SQL)
            for statement in CREATE_INDEXES_SQL:
                cur.execute(statement)
        conn.commit()


def _to_db_value(field_name: str, value: Any) -> Any:
    """Convert Python values to PostgreSQL-friendly values."""
    if value is None:
        return None
    if field_name in BOOLEAN_FIELDS:
        return bool(value)
    return value


def insert_status_report(database_url: str, report: dict[str, Any]) -> int:
    """Append a new status report to PostgreSQL and return the inserted row id."""
    now_ms = int(time.time() * 1000)
    values = [_to_db_value(field, report.get(field)) for field in REPORT_FIELDS]

    columns = ", ".join(("received_at_ms", *REPORT_FIELDS))
    placeholders = ", ".join("%s" for _ in ("received_at_ms", *REPORT_FIELDS))
    sql = f"INSERT INTO status_reports ({columns}) VALUES ({placeholders}) RETURNING id;"

    with get_connection(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, [now_ms, *values])
            row = cur.fetchone()
        conn.commit()

    if row is None:
        raise RuntimeError("PostgreSQL insert failed: no id returned.")
    return int(row["id"])


def fetch_latest_reports_by_rep(database_url: str) -> list[dict[str, Any]]:
    """Return one latest report per rep/device key for the dashboard."""
    sql = """
    WITH normalized AS (
        SELECT
            status_reports.*,
            COALESCE(NULLIF(TRIM(rep_name), ''), device_id) AS rep_key
        FROM status_reports
    ), ranked AS (
        SELECT
            normalized.*,
            ROW_NUMBER() OVER (
                PARTITION BY rep_key
                ORDER BY timestamp_ms DESC, received_at_ms DESC, id DESC
            ) AS rn
        FROM normalized
    )
    SELECT *
    FROM ranked
    WHERE rn = 1
    ORDER BY LOWER(rep_key) ASC;
    """
    with get_connection(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    return [dict(row) for row in rows]


def fetch_reports_for_rep(database_url: str, rep_name: str, limit: int = 50) -> list[dict[str, Any]]:
    """Return the latest reports for a rep/device key, newest first."""
    sql = """
    SELECT
        status_reports.*,
        COALESCE(NULLIF(TRIM(rep_name), ''), device_id) AS rep_key
    FROM status_reports
    WHERE COALESCE(NULLIF(TRIM(rep_name), ''), device_id) = %s
    ORDER BY timestamp_ms DESC, received_at_ms DESC, id DESC
    LIMIT %s;
    """
    with get_connection(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (rep_name, limit))
            rows = cur.fetchall()
    return [dict(row) for row in rows]


def count_distinct_devices(database_url: str) -> int:
    """Return the count of distinct Android device IDs that reported at least once."""
    sql = "SELECT COUNT(DISTINCT device_id) AS total FROM status_reports;"
    with get_connection(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            row = cur.fetchone()
    return int((row or {}).get("total") or 0)
