# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

FastAPI server that receives status reports from Android devices running the ITQAN Call Record Assistant app, stores every report in Neon PostgreSQL, and serves a read-only admin dashboard. Deployed on Koyeb via Docker, database hosted on Neon.

## Development setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# Edit .env with real API_KEY and DATABASE_URL
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Required `.env` variables:
- `API_KEY` — shared secret, sent by Android devices in `X-API-Key` header
- `DATABASE_URL` — Neon PostgreSQL connection string, must include `?sslmode=require`
- `PORT` — defaults to `8000`

## Architecture

**No ORM.** All database access uses raw SQL via `psycopg` (not `psycopg2`).

**Two files, clear separation:**
- [main.py](main.py) — FastAPI app, routes, Pydantic model (`StatusReportIn`), and presentation helpers (`enrich_report`, `time_ago`, `bool_icon`, etc.)
- [database.py](database.py) — all SQL: table/index creation (`init_db`), insert, and three read queries

**Data model — `status_reports` table:**  
Every POST appends a new row; nothing is ever overwritten. The table has no unique constraint on device/rep — history is fully preserved. The `rep_key` used throughout the dashboard is computed dynamically as `COALESCE(NULLIF(TRIM(rep_name), ''), device_id)`, meaning `rep_name` wins if non-empty, otherwise falls back to `device_id`. This computed column is indexed and used in all queries.

**Dashboard queries:**  
`fetch_latest_reports_by_rep` uses a CTE with `ROW_NUMBER() OVER (PARTITION BY rep_key ORDER BY timestamp_ms DESC)` to get one row per rep. `fetch_reports_for_rep` filters by `rep_key` and returns newest-first with a limit.

**Report enrichment:**  
Before passing rows to Jinja2 templates, `enrich_report` in [main.py](main.py) adds computed display fields (`last_seen_ago`, `*_at` formatted timestamps, `alert` flag, `rep_key_url`). Templates never compute these themselves.

**Alert logic** (`is_alert_report`): triggers if last seen > 2 hours ago, `service_running` is false, `permissions_ok` is false, `accessibility_enabled` is false, or `pending_uploads > 10`.

**Authentication:** `POST /api/status` requires `X-API-Key` header matching `API_KEY` env var. Dashboard endpoints (`GET /`, `GET /device/{rep_name}`) have no authentication by design.

**DB connection:** each request opens and closes its own `psycopg.connect` — there is no connection pool. The `DATABASE_URL` is passed explicitly to every database function rather than read from env inside `database.py`.

## Adding new report fields

1. Add the column to `CREATE_REPORTS_TABLE_SQL` in [database.py](database.py)
2. Add the field name to `REPORT_FIELDS` tuple (and `BOOLEAN_FIELDS` if boolean)
3. Add the field to `StatusReportIn` in [main.py](main.py)
4. Re-run `init_db` (happens automatically on next startup via `CREATE TABLE IF NOT EXISTS` — new columns need an `ALTER TABLE` migration instead)
5. Update templates as needed

## Deployment

Koyeb pulls from GitHub `main` branch and builds using the [Dockerfile](Dockerfile). Health check path is `/health`. Port must be `8000`. Environment variables (`API_KEY`, `DATABASE_URL`, `PORT`) are set in Koyeb's service configuration.
