# AGENTS.md

This file guides Codex sessions working in this repository.

## Project Purpose

This is the FastAPI server for the ITQAN Call Record Assistant audit dashboard. Android devices submit status/audit reports, the server appends every report to Neon PostgreSQL, and browser users view a read-only dashboard showing latest device/representative health plus report history.

The Android API contract must remain stable. Dashboard browser authentication is separate from Android API-key authentication.

## Runtime Stack

- FastAPI application served by Uvicorn.
- Jinja2 templates for server-rendered dashboard pages.
- PostgreSQL hosted on Neon.
- Raw SQL via `psycopg`; no ORM.
- Deployed on Render.

## File Map

- `main.py` - FastAPI app, routes, `StatusReportIn`, Basic Auth/API-key auth helpers, response enrichment, no-cache response helpers, and template rendering.
- `database.py` - all PostgreSQL access: table/index creation, inserts, dashboard latest query, detail query, counts, and diagnostics.
- `templates/dashboard.html` - main dashboard page showing one latest report per rep/device.
- `templates/device_detail.html` - report timeline for a single rep/device key.
- `requirements.txt` - Python dependencies: FastAPI, Uvicorn, Jinja2, python-dotenv, and psycopg.
- `.env.example` - documented local/server environment variables.
- `README.md` - setup, deployment, endpoint, and troubleshooting documentation.

## Environment Variables

- `API_KEY` - shared secret used only by Android devices in the `X-API-Key` header for `POST /api/status`.
- `DATABASE_URL` - Neon PostgreSQL connection string. Include `sslmode=require` if Neon requires SSL.
- `DASHBOARD_USERNAME` - username for browser dashboard HTTP Basic Auth.
- `DASHBOARD_PASSWORD` - password for browser dashboard HTTP Basic Auth.
- `PORT` - optional local/server port, defaults to `8000`.

Never expose `API_KEY`, `DATABASE_URL`, or `DASHBOARD_PASSWORD` in logs, rendered pages, JSON diagnostics, commits, screenshots, or documentation examples containing real values.

## Route Contract

- `GET /health` is public and must not require login. Render health checks use this route.
- `POST /api/status` is for Android devices. It requires `X-API-Key` matching `API_KEY`; it must not require dashboard username/password.
- `GET /` is the browser dashboard. It requires dashboard HTTP Basic Auth.
- `GET /device/{rep_name}` is the detail/timeline page. It requires dashboard HTTP Basic Auth.
- `GET /api/latest`, when present, returns latest dashboard data as JSON and should require dashboard HTTP Basic Auth unless a future explicit design says otherwise.
- `GET /debug/db`, when present, should require dashboard HTTP Basic Auth and must avoid leaking secrets.

## Database Behavior

- Reports are append-only. Every accepted Android POST inserts a new row.
- Do not overwrite, upsert, deduplicate, or delete historical reports as part of normal ingest.
- The dashboard shows the latest report per representative/device key.
- The representative/device key is computed as `COALESCE(NULLIF(TRIM(rep_name), ''), device_id)`: non-empty `rep_name` wins, otherwise `device_id`.
- Latest ordering should use server received time first when available, such as `received_at_ms`, `received_at`, or `created_at`; then fall back to Android/device `timestamp_ms`; then a stable tie-breaker such as `id`.
- The detail page should show the latest 50 reports for the selected key, newest first.

## Coding Rules

- Do not add an ORM. Keep PostgreSQL access as raw SQL through `psycopg`.
- Keep SQL helpers in `database.py`; keep route, validation, authentication, and presentation helpers in `main.py`.
- Keep templates simple and server-rendered. Do not add a frontend framework for dashboard refresh behavior.
- Do not break the Android request/response JSON contract for `POST /api/status`.
- Do not expose secrets in logs, pages, JSON responses, or exception messages shown to users.
- Do not require login for `/health`.
- Keep `/api/status` authentication based only on `X-API-Key`.
- Add no-cache headers for dashboard/admin pages and dashboard JSON endpoints that must show fresh data.

## Deployment Notes

Render start command:

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

Neon `DATABASE_URL` usually needs `sslmode=require`, for example:

```text
postgresql://user:password@host/neondb?sslmode=require
```

Android app configuration may use the base Render service URL and append `/api/status` internally. Do not add `:8000` to the Render public URL.

## Testing Checklist

- `GET /health` works without authentication.
- `GET /` requires dashboard username/password.
- `POST /api/status` returns `401` without `X-API-Key`.
- `POST /api/status` accepts a valid JSON report with a valid `X-API-Key`.
- Dashboard shows the latest submitted device/rep.
- Dashboard auto-refresh updates after 60 seconds.
- Device detail page auto-refreshes after 60 seconds.
- `/api/latest` and `/debug/db`, if present, require dashboard login and send no-cache headers.

## Known Pitfalls

- The Android app may use a base server URL and append `/api/status` internally.
- Do not put `:8000` in a Render public URL.
- Browser cache can make the dashboard look stale; use no-cache headers and cache-busting refresh query parameters.
- Render free services can sleep, so the first request after inactivity may be slow.
