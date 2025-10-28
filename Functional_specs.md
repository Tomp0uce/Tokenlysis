# Functional Specifications – Tokenlysis 2.0

## 1. Overview
Tokenlysis adopts a "clean" monolithic strategy: a FastAPI/Python backend orchestrates scorecards, tasks, and real-time delivery while a Next.js 14 frontend powers the typed user experience. The requirements below describe the 0→1 target for this stack.

## 2. Key Features
### 2.1 Backend API
- FastAPI (Pydantic v2) REST endpoints for `/api/users`, `/api/scores`, `/api/files/sign`, `/api/tasks/recalculate`, plus SSE/WebSocket streaming.
- OIDC Bearer authentication + Casbin RBAC. Roles available: `admin`, `user`, `analyst`.
- PostgreSQL persistence through async SQLAlchemy 2. Includes a `User` model with versioned Alembic migrations.
- Dramatiq asynchronous tasks (Redis broker in production, StubBroker in tests) for score recalculation.
- MinIO/S3 object storage with signed POST forms.
- Observability: OpenTelemetry (OTLP), Sentry integration, Prometheus metrics exposed at `/metrics`.
- SQLAdmin interface served at `/admin`.

### 2.2 Real-time
- **SSE** `/api/stream/scores`: periodic broadcast of aggregated scores.
- **WebSocket** `/ws/scores`: interactive subscription with coin filtering.

### 2.3 Frontend
- Next.js (app router) in TypeScript.
- TanStack Query + Orval-generated hooks derived from the FastAPI OpenAPI schema.
- Tailwind + shadcn/ui (Radix) for buttons, forms, and cards.
- React Hook Form + Zod for typed input (theme filter).
- OIDC PKCE (placeholder) with secure token persistence.
- Initial dashboard: top three scores, thematic filter, refresh CTA.

### 2.4 Tests & Quality
- Backend: Pytest + pytest-asyncio + httpx AsyncClient (TDD required).
- Frontend: Vitest + Testing Library.
- Local CI: `ruff`, `black`, `mypy`, `pytest`, `npm test`.

## 3. Non-Functional Requirements
- **Performance**: REST endpoints under 100 ms on the demo dataset; SSE/WS loops remain lightweight.
- **Security**: Bearer tokens validated, Casbin roles centralized, S3 URLs expire quickly.
- **Observability**: optional OTLP traces, injectable Sentry DSN, Prometheus metrics ready for Grafana.
- **Quality**: strongly typed code (strict mypy), async tests covering RBAC/SSE/WS/S3/tasks.

## 4. Data & Task Flows
1. FastAPI requests use an `AsyncSession` obtained through `get_session`.
2. Scheduled recalculations are delegated to Dramatiq (`recalculate_scores`).
3. S3 signatures rely on `generate_presigned_post` (MinIO by default).
4. SQLAdmin lists users for quick auditing.

## 5. Architecture
| Layer | Technology |
|-------|------------|
| API | FastAPI + Pydantic v2 |
| DB | SQLAlchemy 2.0 Async + Alembic |
| Queue | Dramatiq + Redis (stubbed in tests) |
| Real-time | Starlette WebSocket/SSE |
| Auth | OIDC + Casbin |
| Admin | SQLAdmin |
| Storage | MinIO/S3 |
| Observability | OpenTelemetry, Sentry, Prometheus |
| Frontend | Next.js 14, Tailwind, shadcn/ui, TanStack Query |
| Quality | ruff, black, mypy, pytest, vitest |

## 6. Roadmap
- **Immediate MVP**: finalize real OIDC integration, connect Dramatiq to Redis, populate `/api/scores` from SQL computations.
- **Next Iteration**: automate Orval generation, extend the dashboard with real-time charts, add Playwright end-to-end tests.
- **Observability**: export Prometheus/Grafana dashboards and configure Sentry alerting.

## 7. Operational Guides
- Environment variables are prefixed with `TOKENLYSIS_` (see `backend/app/core/config.py`).
- Tests default to SQLite in-memory/temporary databases + StubBroker; production must configure PostgreSQL + Redis.
- Run `orval --config orval.config.ts` against `/openapi.json` to refresh `frontend/lib/api/generated.ts`.

## 8. Compliance
- Never commit secrets; rely on environment variables.
- Contribution rules: TDD, strict typing, synchronized README/Functional_specs documentation.
