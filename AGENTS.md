# AGENTS Instructions

## Project Overview
Tokenlysis is a platform that ranks over 1,000 crypto-assets each day. It computes thematic scores (Community, Liquidity, Opportunity, Security, Technology, Tokenomics) and a global score. A FastAPI backend serves data to interactive vanilla-JS dashboards (market overview, coin detail and sentiment) rendered with ApexCharts.

## Build and Test Commands
- Install backend dependencies: `pip install -r backend/requirements.txt`
- Install Node test dependencies: `npm install`
- Run the API locally: `uvicorn backend.app.main:app --reload`
- Format and lint: `ruff backend && black backend`
- Run backend tests: `pytest`
- Run frontend tests: `node --test tests/*.js`

## Code Style Guidelines
- Python code follows PEP 8 and is formatted with `black` and linted by `ruff`.
- Use type hints for all functions and prefer pure functions in scoring modules.
- Commit messages use the Conventional Commits convention (feat, fix, docs, etc.).
- Toute la logique du planner de design review (hors tests) doit résider dans le fichier `planner.py` à la racine du dépôt.

## Testing Instructions
- Add Pytest unit tests for new Python features and keep coverage close to 80%.
- Add Node `node --test` suites (using jsdom) for new frontend utilities and UI logic.
- Ensure both `pytest` and `node --test tests/*.js` pass before committing.

## Security Considerations
- Never commit secrets or credentials.
- Use HTTPS in production and apply rate limiting on public APIs.
- Store passwords hashed and keep dependencies updated with tools like `pip-audit`.
- Mask secrets in logs and diagnostic endpoints.
- Avoid writing empty environment variables; fall back to defaults when values are blank and raise clear errors for invalid entries.

## Documentation
- Update the README and `Functional_specs.md` when the feature scope evolves.
- Keep roadmap checklists (POC/MVP/EVT) aligned across documentation and actual feature status.
