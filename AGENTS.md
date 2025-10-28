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
