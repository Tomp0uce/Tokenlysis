# Functional Specifications

## 1. Project Overview
Tokenlysis is a public web platform that ranks more than 1,000 crypto-assets using daily computed scores. Each asset receives a global score and thematic subscores (Community, Liquidity, Opportunity, Security, Technology, Tokenomics). Users can view score history, compare assets, and adjust score weights to match their own investment strategy. The site also highlights 100 emerging “trending” assets outside the top 1,000 market-cap list.

## 2. Functional Requirements
### 2.1 Asset Universe & Trending List
- Track the top 1,000 crypto-assets by market capitalization.
- Maintain a secondary list of 100 trending assets outside the top 1,000 using recent activity (price change, volume, search interest, social mentions).

### 2.2 Scoring System
#### 2.2.1 Score Categories
Each asset receives a 0–100 score in the following categories:
- **Community** – Twitter followers, engagement, Telegram/Discord activity.
- **Liquidity** – Market capitalization, 24h volume, number of exchanges, order-book depth.
- **Opportunity** – Technical indicators such as RSI, recent volatility, distance from ATH/ATL.
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
1. **Data Collector**: Python ETL jobs scheduled via APScheduler or Celery beat. Fetches metrics from external APIs and writes to the database.
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
### 6.1 MVP
Focus on ranking and visualisation for a subset of metrics to validate concept.
1. Ingest CoinGecko market data, compute Liquidity and Opportunity scores.
2. Implement global score as average of existing categories.
3. FastAPI backend with endpoints: `/ranking`, `/asset/{id}`, `/history/{id}`.
4. React frontend: ranking table, asset detail page, simple line chart.
5. Basic tests and 60 % coverage.
6. Deployed via Docker Compose on a single VM.

### 6.2 Full Specification
1. Add remaining categories (Community, Security, Technology, Tokenomics) and trending list.
2. Implement custom weight UI and persistence.
3. Historical score charts with price overlay and CSV export.
4. User accounts, authentication, and watchlists.
5. Worker queue for data collection, caching layer, and API rate limiting.
6. Expand tests to 80 % coverage; load tests for ranking endpoint.
7. CI/CD pipeline with staging environment and automated deployments.

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

