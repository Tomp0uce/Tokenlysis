# Tokenlysis 2.0

Tokenlysis now runs on a modern monolithic architecture that combines a FastAPI backend (Pydantic v2, SQLAlchemy 2) with a Next.js/TypeScript frontend. The goal is to offer a clean 0→1 foundation capable of orchestrating crypto score calculations, real-time delivery, and a fully typed user experience.

## Technical Stack

### Backend
- **FastAPI** 0.110 + **Pydantic v2** for typed HTTP and streaming services.
- **SQLAlchemy 2.0** (async) + **Alembic** for PostgreSQL migrations (tests run on SQLite).
- **Dramatiq** (Redis broker in production, stubbed in tests) for asynchronous tasks.
- **WebSockets & SSE** powered by Starlette for real-time score distribution.
- **OIDC authentication** (Keycloak/Okta/Auth0) + **Casbin** for RBAC.
- **SQLAdmin** provides an automatic admin UI based on SQLAlchemy models.
- **Object storage** via an S3-compatible client (MinIO) with signed URLs.
- **Observability**: OpenTelemetry (OTLP), Sentry, Prometheus metrics at `/metrics`.
- **Quality**: `ruff`, `black`, `mypy`, `pytest`, `httpx` for async testing.

### Frontend
- **Next.js 14** (TypeScript, app router).
- **TanStack Query** with Orval-generated hooks to consume the FastAPI OpenAPI schema.
- **Tailwind CSS** + **shadcn/ui** (Radix) for the component library.
- **React Hook Form** + **Zod** for typed form validation.
- **OIDC PKCE** on the client (placeholder implementation) with secure token storage.
- Tests powered by **Vitest** + Testing Library.

## Repository Layout

```
backend/         # FastAPI API, SQLAlchemy models, Dramatiq tasks, observability
backend/alembic  # Alembic migrations (initial users schema)
app/             # Next.js app router (layout + page)
frontend/        # Frontend libraries (Orval hooks, QueryClient, UI components, styles)
tests/           # Pytest suite targeting the 2.0 stack
```

## Getting Started

### Prerequisites
- Python 3.11+
- Node.js 20+
- PostgreSQL & Redis (production) – tests rely on SQLite and Dramatiq's stub broker.

### Backend Installation
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```
Apply database migrations:
```bash
alembic upgrade head
```
The Alembic environment reads `ALEMBIC_DATABASE_URL` first, then `DATABASE_URL`, then the value provided in `alembic.ini`. When
running via `start.sh`, the script exports `ALEMBIC_DATABASE_URL` automatically so SQLite and PostgreSQL deployments stay in
sync. SQLite connections enable Alembic's `render_as_batch` mode to keep `ALTER TABLE` migrations safe.
Run the API:
```bash
uvicorn backend.app.main:app --reload
```
The SQLAdmin dashboard is mounted on `/admin`.

### Frontend Installation
```bash
npm install
npm run dev
```
The frontend expects the API at `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`).

## Quality & Tests

```bash
# Lint & format
ruff check backend
black backend
mypy backend/app

# Backend tests
pytest

# Focused Alembic regression
pytest tests/test_alembic_env.py

# Frontend tests
npm test
```
Running the focused Alembic regression ensures migrations stay synchronous, avoid duplicate `sqlalchemy.url` entries, and never invoke `Base.metadata.create_all` during the bootstrap phase.

## Observability & Operations
- `/metrics` exposes Prometheus counters (via `prometheus_fastapi_instrumentator`).
- Enable OpenTelemetry OTLP and Sentry via `TOKENLYSIS_OTEL_ENDPOINT` and `TOKENLYSIS_SENTRY_DSN`.
- SQLAdmin lives on `/admin` (authentication delegated to the OIDC layer in front of FastAPI).
- Switch Dramatiq to Redis by configuring `dramatiq.set_broker(RedisBroker(...))`.
- Ensure `ALEMBIC_DATABASE_URL` (or `DATABASE_URL`) is exported before running migrations so Alembic uses the synchronous driver.

## Authentication & RBAC
- Use `Authorization: Bearer <token>` headers with OIDC validation (e.g., Keycloak) and Casbin roles defined in `backend/app/core/rbac_policy.csv`.
- Example mapping: the `admin` role can manage users, schedule tasks, sign S3 URLs, and read metrics; the `user` role can subscribe to the score streams.

## File Storage
- `POST /api/files/sign` returns a MinIO/S3 signed POST form for secure uploads.

## Real-time Endpoints
- **SSE** at `/api/stream/scores`.
- **WebSocket** at `/ws/scores`.

## Orval Client Generation
- See `frontend/lib/api/generated.ts` for the generated hooks.
- Regenerate by running `orval --config orval.config.ts` against the FastAPI OpenAPI schema.

## License
Proprietary Tokenlysis software. Commercial usage requires written approval.
