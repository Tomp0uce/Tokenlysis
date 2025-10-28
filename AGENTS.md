# AGENTS Instructions

## Project Overview
Tokenlysis 2.0 is a single FastAPI + Next.js monolith. The FastAPI backend (Pydantic v2, SQLAlchemy 2, Dramatiq, Casbin, SQLAdmin, MinIO, OpenTelemetry/Sentry/Prometheus) serves REST, SSE, and WebSocket endpoints. The Next.js 14 frontend (TypeScript, Tailwind, shadcn/ui, TanStack Query, React Hook Form + Zod) consumes the OpenAPI specification through Orval-generated hooks.

## Build & Test Commands
- Install backend dependencies: `pip install -r backend/requirements.txt`
- Run migrations: `alembic upgrade head`
- Start the API: `uvicorn backend.app.main:app --reload`
- Lint & format: `ruff check backend && black backend`
- Type-check: `mypy backend/app`
- Backend tests: `pytest`
- Frontend install: `npm install`
- Frontend tests: `npm test`

## Code Style
- Python: PEP 8, formatted with `black` (line length 100), linted with `ruff`, typed with strict `mypy`.
- TypeScript: follow Next.js/ESLint conventions, functional components, TanStack Query hooks.
- Never commit secrets; configuration must come from `TOKENLYSIS_*` environment variables.

## Testing & TDD
- Every new feature starts with a failing Pytest or Vitest specification.
- Required coverage: RBAC, SSE/WS, Dramatiq tasks, S3 signing, and UI flows backed by React Query.

## Documentation
- Keep `README.md` and `Functional_specs.md` aligned with the active stack.
- Summarize major architectural or command changes in the PR message.

## Security
- OIDC authentication is mandatory (use placeholder tokens in tests).
- Casbin drives RBAC; protect every sensitive route.
- Generate expiring S3 pre-signed URLs only.

## Assistant Responsibilities
- Preserve the synchronous Alembic bootstrap that now powers SQLite deployments via `ALEMBIC_DATABASE_URL`.
- Keep test coverage for `backend/alembic/env.py` aligned with `tests/test_alembic_env.py` when the migration flow changes.
- Update documentation (README, Functional_specs) whenever the database bootstrap or environment contract changes.

## Decision Rules
- Prefer `ALEMBIC_DATABASE_URL` when present; otherwise fall back to `DATABASE_URL`, and only then to the value in `alembic.ini`.
- Enable `render_as_batch` automatically for SQLite dialects to ensure ALTER TABLE compatibility.
- Use synchronous SQLAlchemy engines for Alembic runs unless the configured URL uses an async driver.

## Command / IO Contract
- `start.sh` must export `ALEMBIC_DATABASE_URL` before executing `alembic upgrade head` and `uvicorn`.
- Alembic relies on `alembic.ini` resolving `${ALEMBIC_DATABASE_URL}`; deployments must export the variable or supply a fallback.

## Maintenance Notes
- The Alembic environment module defers automatic execution when imported outside an Alembic run—tests should patch the module-level `context` and `config` accordingly.
- The regression tests in `tests/test_alembic_env.py` validate env-var precedence, batch mode, and the synchronous engine contract.
- Additional guards ensure `backend/alembic/env.py` never reintroduces `async_engine_from_config` nor calls `Base.metadata.create_all`; keep those tests green when modifying migration plumbing.
