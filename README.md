# MediFleet — Multi-Hospital Management Platform

MediFleet is a multi-tenant SaaS platform for running an entire fleet of hospitals from one codebase. Each hospital is **fully isolated** — its own PostgreSQL database, its own admin, its own staff — while the MediFleet platform team manages the fleet itself from a dedicated superadmin console.

- **Master DB** (`hms_master`) — superadmins and the tenant registry. One per platform.
- **Tenant DBs** — one PostgreSQL database per hospital. Identical schema, fully isolated data. Tenants are routed by the `X-Tenant-ID` header, which must match the caller's auth token.

## 🚀 Features

MediFleet ships as a set of toggleable **modules**. Some are always on; most can be enabled per hospital.

**Core (always on)**
- **Authentication & RBAC** — JWT login, refresh, password reset, role/permission management.
- **Patient Registry** — register, search, and manage patient records and demographics.
- **Appointments** — booking, scheduling, and live department queues (real-time via WebSocket).
- **Dashboard** — role-based home page and per-worker agenda.
- **Internal Messaging & Notifications** — staff-to-staff messaging plus system/clinical alerts.
- **Settings & Support** — account, branding, security settings, and an in-app helpdesk to the MediFleet team.

**Optional (toggle per hospital)**
- **Clinical Desk** — encounters, diagnoses, prescriptions, triage.
- **Laboratory & Radiology** — orders, results/reports, billing integration.
- **Pharmacy** — dispensing, stock movement, alerts.
- **Inventory** — stores, suppliers, purchase orders.
- **Wards & In-Patient** — bed management, admissions, rounds.
- **Billing** — invoicing, statements, payment plans, cheque receipting & reconciliation.
- **Managerial Accounting** — chart of accounts, journals, budgets, debtors, financial statements.
- **M-Pesa Payments (Pay Hero)** — mobile-money collections at the till and pharmacy.
- **Analytics** — aggregated dashboards and reports.
- **Patient Portal** — self-service portal for patients.
- **Medical History** — longitudinal patient history.
- **Referrals** — inbound and outbound referrals.
- **Branding** — logos, colours, document templates.
- **Privacy** — consent, DSAR, audit logs.

## 🛠️ Technology Stack

### Backend
- **Framework**: [FastAPI](https://fastapi.tiangolo.com/) (Python)
- **Database**: PostgreSQL with [SQLAlchemy 2.0](https://www.sqlalchemy.org/) ORM (per-tenant engines, intended to sit behind PgBouncer)
- **Migrations**: [Alembic](https://alembic.sqlalchemy.org/)
- **Cache / Real-time**: Redis, WebSockets
- **Security**: Passlib (Bcrypt), Python-JOSE (JWT), SlowAPI (rate limiting)
- **Payments**: Pay Hero (M-Pesa) — custody-free per-tenant hospital rail + platform subscription rail
- **Email**: Resend over SMTP (outbound) + inbound support→ticket pipeline

### Frontend
- **Framework**: [React 19](https://react.dev/) + [Vite](https://vitejs.dev/)
- **Styling**: [Tailwind CSS](https://tailwindcss.com/) (with dark mode)
- **Routing**: React Router DOM
- **Icons & UI**: Lucide React, React Hot Toast
- **HTTP Client**: Axios

### Deployment
- **Frontend**: Vercel (SPA) → `https://www.medifleet.app`
- **Backend**: Render (FastAPI) — see `render.yaml`
- **Local**: Docker Compose (Postgres + Redis + backend + frontend) — see `docker-compose.yml`

## ⚙️ Setup & Installation

### Prerequisites
- Python 3.9+
- Node.js 18+
- PostgreSQL server (local or remote)
- Redis (optional locally; used for cache and real-time)

### Quick start with Docker

```bash
cp .env.example .env   # fill in secrets
docker compose up --build
```

This brings up Postgres, Redis, the backend, and the frontend together.

### Manual setup

#### 1. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file in `backend/` (see `.env.example` at the repo root) and configure your `DATABASE_URL`, JWT secret, and any module integrations.

Run migrations and seed demo data:

```bash
alembic upgrade head
python seed_demo.py
```

> When tenant models change, run `python scripts/migrate_all_tenants.py` to apply schema patches across every tenant database (and the master DB).

#### 2. Frontend

```bash
cd frontend
npm install
```

## 🏃 Running the Application

Run the backend and frontend in separate terminals.

**Backend:**
```bash
cd backend
source venv/bin/activate        # Windows: venv\Scripts\activate
uvicorn app.main:app --reload
```
The API is served at `http://localhost:8000`. Interactive API docs (Swagger UI) are at `http://localhost:8000/docs`.

**Frontend:**
```bash
cd frontend
npm run dev
```
The app is served at `http://localhost:5173`.

## 🧪 Tests

```bash
# Backend (pytest against a live server)
cd backend && pytest

# Frontend (Vitest + React Testing Library)
cd frontend && npm test
```

## 📚 Documentation

Additional docs live in [`docs/`](docs/):
- `DEPLOYMENT.md` — production deployment (incl. the PgBouncer recipe)
- `LAUNCH_READINESS.md` — go-live checklist
- `USE_CASES.md`, `TRAINING.md`, `usermanuals/` — product and operator guides

## 📄 License

See [LICENSE](LICENSE).
