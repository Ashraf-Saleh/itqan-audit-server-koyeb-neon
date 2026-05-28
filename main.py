"""FastAPI application for the ITQAN Call Record Assistant audit server."""

from __future__ import annotations

import os
import secrets
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field, field_validator

from database import (
    REPORT_FIELDS,
    check_database,
    count_distinct_devices,
    fetch_latest_reports_by_rep,
    fetch_reports_for_rep,
    init_db,
    insert_status_report,
)

load_dotenv()

API_KEY = os.getenv("API_KEY", "change_me_secret")
DATABASE_URL = os.getenv("DATABASE_URL", "")
PORT = int(os.getenv("PORT", "8000"))
DASHBOARD_USERNAME = os.getenv("DASHBOARD_USERNAME", "admin")
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "change_me_dashboard_password")

app = FastAPI(
    title="ITQAN Call Record Assistant Audit Server",
    version="1.0.0",
    description="Receives real-time Android device status reports and shows a live admin dashboard.",
)
templates = Jinja2Templates(directory="templates")
dashboard_security = HTTPBasic()


class StatusReportIn(BaseModel):
    """Validated payload accepted by POST /api/status.

    Only device_id and timestamp_ms are required. Extra unknown fields are rejected
    so device-side payload changes are caught early during testing.
    """

    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(..., min_length=1, max_length=255)
    rep_name: str | None = Field(default=None, max_length=120)
    app_version: str | None = Field(default=None, max_length=80)
    timestamp_ms: int = Field(..., ge=0)

    service_running: bool | None = None
    consent_accepted: bool | None = None
    permissions_ok: bool | None = None
    accessibility_enabled: bool | None = None
    all_files_access: bool | None = None
    google_account_connected: bool | None = None
    drive_folder_configured: bool | None = None
    sheet_configured: bool | None = None

    last_call_start_ms: int | None = Field(default=None, ge=0)
    last_call_direction: str | None = Field(default=None, max_length=50)
    last_call_duration_seconds: int | None = Field(default=None, ge=0)
    pending_uploads: int | None = Field(default=None, ge=0)
    total_uploaded: int | None = Field(default=None, ge=0)
    last_upload_ms: int | None = Field(default=None, ge=0)
    last_sync_ms: int | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("device_id", "rep_name", "app_version", "last_call_direction", "notes", mode="before")
    @classmethod
    def normalize_strings(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


@app.on_event("startup")
def on_startup() -> None:
    """Initialize PostgreSQL tables when the app starts."""
    init_db(DATABASE_URL)


def verify_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    """Validate the shared API key for write endpoints."""
    if not x_api_key or x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key.",
        )


def verify_dashboard_login(credentials: HTTPBasicCredentials = Depends(dashboard_security)) -> str:
    """Protect read-only dashboard/admin endpoints with simple HTTP Basic auth."""
    username_ok = secrets.compare_digest(credentials.username, DASHBOARD_USERNAME)
    password_ok = secrets.compare_digest(credentials.password, DASHBOARD_PASSWORD)

    if not (username_ok and password_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid dashboard username or password.",
            headers={"WWW-Authenticate": "Basic"},
        )

    return credentials.username


def utc_datetime_from_ms(timestamp_ms: int | None) -> str:
    """Format epoch milliseconds as a UTC timestamp for the dashboard."""
    if timestamp_ms is None:
        return "—"
    try:
        return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except (OSError, OverflowError, ValueError):
        return "Invalid timestamp"


def time_ago(timestamp_ms: int | None) -> str:
    """Return a compact human-readable relative time, such as '5 min ago'."""
    if timestamp_ms is None:
        return "—"

    now_ms = int(time.time() * 1000)
    delta_seconds = max(0, int((now_ms - timestamp_ms) / 1000))

    if delta_seconds < 60:
        return f"{delta_seconds} sec ago"
    minutes = delta_seconds // 60
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hr ago"
    days = hours // 24
    return f"{days} day{'s' if days != 1 else ''} ago"


def bool_icon(value: Any) -> str:
    """Render bool-like DB values as dashboard icons."""
    if value is None:
        return "—"
    return "✓" if bool(value) else "✗"


def bool_class(value: Any) -> str:
    """CSS class for bool-like DB values."""
    if value is None:
        return "muted"
    return "ok" if bool(value) else "bad"


def is_alert_report(report: dict[str, Any]) -> bool:
    """Return True if a latest report should be highlighted as an alert."""
    now_ms = int(time.time() * 1000)
    last_seen_too_old = (now_ms - int(report.get("timestamp_ms") or 0)) > (2 * 60 * 60 * 1000)

    return any(
        (
            last_seen_too_old,
            report.get("service_running") == 0,
            report.get("permissions_ok") == 0,
            report.get("accessibility_enabled") == 0,
            int(report.get("pending_uploads") or 0) > 10,
        )
    )




def apply_no_cache_headers(response: HTMLResponse) -> HTMLResponse:
    """Prevent browser/proxy caching so manual refresh shows the latest database rows."""
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

def enrich_report(report: dict[str, Any]) -> dict[str, Any]:
    """Add presentation-friendly calculated fields to one report row."""
    enriched = dict(report)
    rep_key = enriched.get("rep_key") or enriched.get("rep_name") or enriched.get("device_id")
    enriched["rep_key"] = rep_key
    enriched["rep_key_url"] = quote(str(rep_key), safe="")
    enriched["last_seen_ago"] = time_ago(enriched.get("timestamp_ms"))
    enriched["last_seen_at"] = utc_datetime_from_ms(enriched.get("timestamp_ms"))
    enriched["last_call_at"] = utc_datetime_from_ms(enriched.get("last_call_start_ms"))
    enriched["last_upload_at"] = utc_datetime_from_ms(enriched.get("last_upload_ms"))
    enriched["last_sync_at"] = utc_datetime_from_ms(enriched.get("last_sync_ms"))
    enriched["received_at"] = utc_datetime_from_ms(enriched.get("received_at_ms"))
    enriched["alert"] = is_alert_report(enriched)
    return enriched


@app.post("/api/status")
def receive_status_report(
    report: StatusReportIn,
    _: None = Depends(verify_api_key),
) -> dict[str, bool]:
    """Receive and store one Android status report."""
    payload = report.model_dump()
    insert_status_report(DATABASE_URL, payload)
    return {"ok": True}




@app.get("/api/latest")
def latest_reports_api(_: str = Depends(verify_dashboard_login)) -> dict[str, Any]:
    """Return latest dashboard rows as JSON for quick operational verification."""
    rows = [enrich_report(row) for row in fetch_latest_reports_by_rep(DATABASE_URL)]
    return {
        "ok": True,
        "server_time_ms": int(time.time() * 1000),
        "count": len(rows),
        "reports": rows,
    }


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, dashboard_username: str = Depends(verify_dashboard_login)) -> HTMLResponse:
    """Render the live admin dashboard with one latest row per rep/device."""
    server_time_ms = int(time.time() * 1000)
    db_error: str | None = None
    latest_reports: list[dict[str, Any]] = []
    total_device_count = 0

    try:
        latest_reports = [enrich_report(row) for row in fetch_latest_reports_by_rep(DATABASE_URL)]
        total_device_count = count_distinct_devices(DATABASE_URL)
    except Exception as exc:  # noqa: BLE001 - show safe operational error on dashboard
        db_error = f"{type(exc).__name__}: {exc}"

    response = templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "reports": latest_reports,
            "server_time": utc_datetime_from_ms(server_time_ms),
            "total_device_count": total_device_count,
            "db_error": db_error,
            "dashboard_username": dashboard_username,
            "bool_icon": bool_icon,
            "bool_class": bool_class,
        },
    )
    return apply_no_cache_headers(response)


@app.get("/device/{rep_name}", response_class=HTMLResponse)
def device_detail(request: Request, rep_name: str, dashboard_username: str = Depends(verify_dashboard_login)) -> HTMLResponse:
    """Render the latest 50 reports for one rep/device key."""
    reports = [enrich_report(row) for row in fetch_reports_for_rep(DATABASE_URL, rep_name, limit=50)]
    return templates.TemplateResponse(
        request,
        "device_detail.html",
        {
            "rep_name": rep_name,
            "reports": reports,
            "fields": ("id", "received_at_ms", *REPORT_FIELDS),
            "server_time": utc_datetime_from_ms(int(time.time() * 1000)),
            "dashboard_username": dashboard_username,
            "bool_icon": bool_icon,
            "bool_class": bool_class,
        },
    )


@app.get("/health")
def health() -> dict[str, bool]:
    """Simple health endpoint for uptime monitors."""
    return {"ok": True}


@app.get("/debug/db")
def debug_database(_: str = Depends(verify_dashboard_login)) -> dict[str, Any]:
    """Safe database diagnostic endpoint. Remove or protect later if needed."""
    result = check_database(DATABASE_URL)
    result["database_url_configured"] = bool(DATABASE_URL)
    return result


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
