# ITQAN Audit Server — Koyeb + Neon + GitHub

FastAPI web application that receives real-time status reports from Android devices running the **ITQAN Call Record Assistant** app, stores every report in **Neon PostgreSQL**, and shows a live read-only admin dashboard.

This version is optimized for:

```text
GitHub repository
    ↓ auto deploy
Koyeb Web Service
    ↓ DATABASE_URL
Neon PostgreSQL
```

No ORM is used. Database access is raw SQL through `psycopg`.

---

## Features

- `POST /api/status` accepts Android device status reports.
- Shared secret authentication using `X-API-Key`.
- PostgreSQL storage using raw SQL, no ORM.
- Full history is preserved: every report is appended, not overwritten.
- Dashboard at `GET /` shows one latest row per representative/device.
- Dashboard and admin JSON/debug pages are protected with simple HTTP Basic username/password from environment variables.
- Detail page at `GET /device/{rep_name}` shows the latest 50 reports.
- Alert highlighting when:
  - Last seen is older than 2 hours.
  - `service_running = false`.
  - `permissions_ok = false`.
  - `accessibility_enabled = false`.
  - `pending_uploads > 10`.
- Pages auto-refresh every 30 seconds.
- Dashboard timestamps are displayed in `Africa/Cairo` local time.
- `/health` endpoint for Koyeb health checks.
- Includes a `Dockerfile` for reliable Koyeb deployment.

---

## Project structure

```text
itqan-audit-server/
├── main.py
├── database.py
├── Dockerfile
├── .dockerignore
├── templates/
│   ├── dashboard.html
│   └── device_detail.html
├── .env.example
├── .gitignore
├── .python-version
├── requirements.txt
└── README.md
```

---

## 1) Create the Neon PostgreSQL database

1. Create/login to your Neon account.
2. Create a new project, for example: `itqan-audit`.
3. Open **Connect** / **Connection Details**.
4. Copy the PostgreSQL connection string.
5. Make sure it contains SSL, usually like this:

```text
postgresql://user:password@ep-example.neon.tech/neondb?sslmode=require
```

Some Neon connection strings may include `channel_binding=require`; this is also fine:

```text
postgresql://user:password@ep-example.neon.tech/neondb?sslmode=require&channel_binding=require
```

This value will be used as `DATABASE_URL` in local `.env` and in Koyeb environment variables.

---

## 2) Run locally first

### Windows PowerShell

```powershell
cd itqan-audit-server
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Then edit `.env`:

```env
API_KEY=your_strong_secret_key
DATABASE_URL=postgresql://user:password@ep-example.neon.tech/neondb?sslmode=require
PORT=8000
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=change_this_dashboard_password
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=change_this_dashboard_password
```

Run the server:

```powershell
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### macOS / Linux

```bash
cd itqan-audit-server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Then edit `.env`:

```env
API_KEY=your_strong_secret_key
DATABASE_URL=postgresql://user:password@ep-example.neon.tech/neondb?sslmode=require
PORT=8000
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=change_this_dashboard_password
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=change_this_dashboard_password
```

Run the server:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open:

```text
http://localhost:8000
```

---

## 3) Test POST locally with curl

Replace `your_strong_secret_key` with the value in `.env`.

```bash
curl -X POST "http://localhost:8000/api/status" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_strong_secret_key" \
  -d '{
    "device_id": "Infinix X6725 / Android build ID",
    "rep_name": "Ahmed_Khaled",
    "app_version": "0.2.0-drive-audit",
    "timestamp_ms": 1716728400000,
    "service_running": true,
    "consent_accepted": true,
    "permissions_ok": true,
    "accessibility_enabled": true,
    "all_files_access": true,
    "google_account_connected": true,
    "drive_folder_configured": true,
    "sheet_configured": true,
    "last_call_start_ms": 1716728000000,
    "last_call_direction": "outgoing",
    "last_call_duration_seconds": 245,
    "pending_uploads": 3,
    "total_uploaded": 47,
    "last_upload_ms": 1716727000000,
    "last_sync_ms": 1716727500000,
    "notes": "local test"
  }'
```

Expected response:

```json
{"ok": true}
```

Then refresh:

```text
http://localhost:8000
```

---

## 4) Push the project to GitHub

Create a new empty GitHub repository, for example:

```text
itqan-audit-server
```

Then from inside the project folder:

```bash
git init
git add .
git commit -m "Initial ITQAN audit server for Koyeb and Neon"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/itqan-audit-server.git
git push -u origin main
```

Important: do **not** commit `.env`. It is already ignored by `.gitignore`.

---

## 5) Deploy to Koyeb from GitHub

1. Create/login to your Koyeb account.
2. Click **Create Web Service**.
3. Choose **GitHub** as the deployment method.
4. Install/authorize the Koyeb GitHub app if requested.
5. Select your repository: `itqan-audit-server`.
6. Choose branch: `main`.
7. Choose **Dockerfile** as the builder if Koyeb asks for builder type.
8. Confirm the exposed port is `8000`.
9. Add environment variables:

```env
API_KEY=your_strong_secret_key
DATABASE_URL=postgresql://user:password@ep-example.neon.tech/neondb?sslmode=require
PORT=8000
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=change_this_dashboard_password
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=change_this_dashboard_password
```

10. Set health check path to:

```text
/health
```

11. Click **Deploy**.

After deployment, Koyeb will give you a public URL similar to:

```text
https://your-service-name-your-org.koyeb.app
```

Open the dashboard:

```text
https://your-service-name-your-org.koyeb.app/
```

---

## 6) Test the deployed Koyeb endpoint

```bash
curl -X POST "https://your-service-name-your-org.koyeb.app/api/status" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_strong_secret_key" \
  -d '{
    "device_id": "Test Android Device",
    "rep_name": "Test_Rep",
    "app_version": "0.2.0-drive-audit",
    "timestamp_ms": 1716728400000,
    "service_running": true,
    "permissions_ok": true,
    "accessibility_enabled": true,
    "all_files_access": true,
    "google_account_connected": true,
    "drive_folder_configured": true,
    "sheet_configured": true,
    "pending_uploads": 0,
    "total_uploaded": 1,
    "notes": "koyeb test"
  }'
```

Expected response:

```json
{"ok": true}
```

Then open the dashboard and check that `Test_Rep` appears.

---

## 7) Android app configuration

In the Android app, configure:

```text
Status API URL:
https://your-service-name-your-org.koyeb.app/api/status
```

Add this HTTP header in every status POST:

```text
X-API-Key: your_strong_secret_key
```

Send status every 15 minutes and on app start/stop.

---

## 8) Dashboard login

The dashboard uses simple browser HTTP Basic authentication. Set these environment variables in Render or your local `.env`:

```env
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=change_this_dashboard_password
```

Protected read-only/admin endpoints:

```text
/
/device/{rep_name}
/api/latest
/debug/db
```

Public endpoints:

```text
/health
```

Android write endpoint still uses API key authentication only:

```text
POST /api/status
Header: X-API-Key
```

For production, also keep Render/Cloudflare access controls if needed.

---

## Troubleshooting

### `RuntimeError: DATABASE_URL is not configured`

Set `DATABASE_URL` in `.env` locally or in Koyeb environment variables.

### Neon SSL error

Make sure the connection string contains:

```text
?sslmode=require
```

or:

```text
?sslmode=require&channel_binding=require
```

### `401 Missing or invalid API key`

Check that the Android app or curl request sends:

```text
X-API-Key: the_same_value_as_API_KEY
```

### Dashboard is empty

Send one test POST request first. The dashboard only shows reps/devices that have posted at least one report.

### Koyeb deployment fails on port

Make sure the service port is `8000`. The Dockerfile starts the app using:

```bash
uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
```

## Dashboard refresh / cache note

This version adds cache-control headers to the dashboard and detail pages so manual browser refresh shows the latest PostgreSQL rows.

The dashboard auto-refreshes every 30 seconds. You can also verify latest rows directly as JSON:

```text
https://YOUR_RENDER_SERVICE.onrender.com/api/latest
```

### Dashboard asks for username/password

Use the values configured in Render Environment:

```env
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=your_dashboard_password
```

If the browser keeps asking again, the username or password is wrong. Update the Render environment variables and redeploy.
