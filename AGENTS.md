# AGENTS Instructions

## Project Overview
Tokenlysis is a platform that ranks over 1,000 crypto-assets each day. It computes thematic scores (Community, Liquidity, Opportunity, Security, Technology, Tokenomics) and a global score. A simple FastAPI backend serves data to a static frontend table.

## Build and Test Commands
- Install backend dependencies: `pip install -r backend/requirements.txt`
- Run the API locally: `uvicorn backend.app.main:app --reload`
- Format and lint: `ruff backend && black backend`
- Run tests: `pytest`

## Code Style Guidelines
- Python code follows PEP 8 and is formatted with `black` and linted by `ruff`.
- Use type hints for all functions and prefer pure functions in scoring modules.
- Commit messages use the Conventional Commits convention (feat, fix, docs, etc.).

## Testing Instructions
- Add Pytest unit tests for new Python features and keep coverage close to 80%.
- Ensure `pytest` passes before committing. Frontend tests will be added with Jest in future phases.

## Security Considerations
- Never commit secrets or credentials.
- Use HTTPS in production and apply rate limiting on public APIs.
- Store passwords hashed and keep dependencies updated with tools like `pip-audit`.
- Mask secrets in logs and diagnostic endpoints.

## Documentation
- Update the README when the feature scope evolves.
