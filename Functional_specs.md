# Functional Specifications

## 1. Project Overview
Tokenlysis is a public web platform that aims to rank more than 1,000 crypto-assets using daily computed scores. The current proof of concept focuses on a configurable top ``N`` assets (default 20) with **Liquidity**, **Opportunity** and global scores refreshed at 00:00 UTC. Users can view score history and explore a static ranking table. Highlighting 100 trending assets and additional categories are planned for the MVP.

## 2. Functional Requirements
### 2.1 Asset Universe & Trending List
- **POC**: configurable top ``N`` assets (default 20).
- **MVP**: track the top 1,000 crypto-assets by market capitalization and maintain a secondary list of 100 trending assets outside the top 1,000 using recent activity (price change, volume, search interest, social mentions).

### 2.2 Scoring System
#### 2.2.1 Score Categories
Each asset receives a 0–100 score. The POC implements the following:
- **Liquidity** – Market capitalization, 24h volume, number of exchanges, order-book depth.
- **Opportunity** – Technical indicators such as RSI, recent volatility, distance from ATH/ATL.

The MVP will add the remaining categories:
- **Community** – Twitter followers, engagement, Telegram/Discord activity.
- **Security** – Audit history, time since launch without major incidents, decentralisation level.
- **Technology** – GitHub commits, active contributors, release cadence, documentation quality.
- **Tokenomics** – Supply distribution, fully-diluted market cap, inflation/burn mechanics, token unlock schedule.

#### 2.2.2 Data Parameters
Approximately 100 raw metrics are gathered daily for each asset from sources including CoinGecko, CoinMarketCap, Twitter API, GitHub API, and DeFiLlama. Data is refreshed once per day at 00:00 UTC.

#### 2.2.3 Normalisation & Weighting
- Each metric is transformed to a 0–100 scale using log-scaling, min–max, or threshold-based functions.
- Category scores are weighted averages of their metrics. Default weights: Community 15%, Liquidity 20%, Opportunity 20%, Security 15%, Technology 15%, Tokenomics 15%.
- Users can customise category weights; the system normalises user weights to 100% before aggregating.

#### 2.2.4 History & Backtesting
- Store daily values of category and global scores for every asset.
- Expose endpoints to fetch score history for charts and CSV export.
- Allow comparisons of multiple assets and overlay of price data for backtesting strategies.

### 2.3 User Interface
- **Home/Ranking**: searchable table with global score, category subscores, price, and filters.
- **Asset Detail**: radar chart of current subscores, historical line charts for scores and price.
- **Custom Weights**: slider-based UI to adjust category weights and persist user preferences.
- **Responsive Design**: cards on mobile, tables and advanced filters on desktop.
- **Dark/Light Themes**.

### 2.4 Accounts & API
- Optional user accounts for saving custom weights and watchlists.
- Public REST API with endpoints for ranking, asset details, and score history.

## 3. Non‑Functional Requirements
- **Performance**: serve ranking requests for 1,100 assets in <200 ms; nightly data ingestion completes within 30 minutes.
- **Scalability**: architecture supports adding new metrics without downtime.
- **Security**: HTTPS only, rate limiting on public API, hashed user passwords, regular dependency scans.
- **Accessibility**: WCAG 2.1 AA, keyboard navigation, descriptive alt text.

## 4. System Architecture
### 4.1 Components
1. **Data Collector**: Python ETL jobs scheduled via APScheduler or Celery beat. Fetches metrics from external APIs and writes to the database. In development mode, seed asset symbols are translated to real CoinGecko IDs via `seed_mapping.py`; production environments obtain IDs directly from the CoinGecko `/coins/list` endpoint.
2. **Scoring Service**: Python module that normalises metrics and computes category/global scores.
3. **API Backend**: FastAPI application exposing REST endpoints and serving score calculations.
4. **Frontend**: React application (TypeScript + Vite) consuming the API.
5. **Database**: PostgreSQL for persistent storage; Redis for caching hot ranking results.
6. **Worker Queue**: Celery workers for heavy computations and asynchronous tasks.
7. **Containerisation**: Docker & Docker Compose for local development and deployment.

### 4.2 Data Flow
1. Scheduler triggers data collectors each day at 00:00 UTC.
2. Raw metrics stored in PostgreSQL.
3. Scoring service reads metrics, computes scores, and stores results with timestamps.
4. API serves ranking and historical data to frontend and external clients.
5. User custom weights are stored per account and applied on demand.

### 4.3 Deployment
- Production uses Docker images orchestrated by Kubernetes or Docker Compose.
- CI/CD pipeline builds images, runs tests, and deploys to staging then production.

## 5. Technology Choices
| Layer | Technology |
|------|------------|
| Backend | Python 3.11, FastAPI, Pydantic, SQLAlchemy |
| Data Processing | Pandas, NumPy, Celery, APScheduler |
| Database | PostgreSQL 15, Redis 7 |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS |
| Testing | Pytest, Jest + React Testing Library |
| DevOps | Docker, Docker Compose, GitHub Actions |

## 6. Development Phases
### 6.1 Proof of Concept (POC)
Demonstrate the scoring concept with a minimal feature set deployable via Docker Compose.
1. Ingest CoinGecko market data and compute **Liquidity** and **Opportunity** scores.
2. Aggregate a global score from the available categories.
3. Expose FastAPI endpoints: `/ranking`, `/asset/{id}`, and `/history/{id}`.
4. Serve a static frontend table from the backend.
5. Provide a `docker-compose.yml` that runs the backend and frontend together, including an example for Synology NAS Container Manager.

### 6.2 Minimum Viable Product (MVP)
Build a usable platform with core functionality and persistent storage.
1. Add remaining score categories (Community, Security, Technology, Tokenomics).
2. Detect and display 100 trending assets outside the top 1,000. *(MVP)*
3. Introduce PostgreSQL persistence for metrics and scores.
4. Implement basic charts and user-defined weighting in the frontend.
5. Ensure 60 % test coverage and nightly data refresh jobs.

### 6.3 Engineering Validation Test (EVT)
Harden the system for wider adoption and prepare for production.
1. Add user accounts, authentication, and watchlists.
2. Implement a worker queue, caching layer, and API rate limiting.
3. Provide historical score charts with price overlays and CSV export.
4. Expand tests to 80 % coverage and add load testing for ranking endpoints.
5. Set up a CI/CD pipeline with staging environment and automated deployments.

## 7. Coding Standards & Guidelines
- **Style**: PEP 8 for Python (enforced by `ruff` and `black`); ESLint + Prettier for TypeScript.
- **Structure**: prefer pure functions in scoring; separate layers (API, services, repositories).
- **Type Hints**: mandatory for all public functions; enable mypy for static typing.
- **Commits**: Conventional Commits (feat, fix, docs, etc.).
- **Testing**: Pytest and Jest with coverage reports; minimum 80 % line coverage before merge.
- **Code Review**: all changes require PR review and passing CI.
- **Security**: run `pip-audit` and `npm audit` in CI.

## 8. Future Enhancements
- Integrate on-chain analytics providers.
- Machine-learning based anomaly detection on scores.
- Multi-language UI.
- Mobile applications using React Native.

