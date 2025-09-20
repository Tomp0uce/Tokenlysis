# Functional Specifications

## 1. Project Overview
Tokenlysis is a public web platform that ranks a configurable top ``N`` cryptocurrencies using CoinGecko market data. The proof of concept focuses on the top 50 assets, computes **Liquidity**, **Opportunity** and a derived **Global** score, and refreshes data every 12 hours through a background ETL loop. A static dashboard built with vanilla JavaScript consumes the public API and displays a sortable table enriched with category badges and freshness indicators.

## 2. Current Functional Scope
### 2.1 Asset Universe & Data Freshness
- Configurable universe controlled by `CG_TOP_N` (default 50) sourced from CoinGecko.
- Background ETL fetches markets on startup and then at the cadence defined by `REFRESH_GRANULARITY` (default 12 h).
- Fallback to bundled seed data when the live fetch fails and `USE_SEED_ON_FAILURE` is enabled.

### 2.2 Scoring System
- **Liquidity** – Log-scaled normalisation of market cap, 24 h volume and exchange listings.
- **Opportunity** – Relative Strength Index (RSI) and day-over-day volume change, with RSI inverted above 70 to highlight oversold assets.
- **Global** – Mean of available category scores, ignoring missing components.
- Scores are persisted alongside market snapshots to power historical analysis in future iterations.

### 2.3 Category Management
- CoinGecko categories are cached per asset with a 24-hour freshness threshold.
- Categories are stored as JSON payloads in the `coins` table and exposed through `/api/coins/{coin_id}/categories` and the markets endpoint.
- Slugs derived from category names provide stable identifiers when CoinGecko lacks explicit IDs.

### 2.4 Public API
- `GET /api/markets/top` – list latest market snapshots, clamping `limit` to `[1, CG_TOP_N]` and enforcing `vs=usd` (returns data source, last refresh timestamp and stale flag).
- `GET /api/price/{coin_id}` – retrieve a single asset snapshot or `404` when unavailable.
- `GET /api/coins/{coin_id}/categories` – expose cached category names and IDs.
- `GET /api/diag` – diagnostics including CoinGecko plan, effective base URL, refresh interval, last ETL item count, persisted call budget and configured universe size.
- `GET /api/last-refresh` – lightweight endpoint returning only the last refresh timestamp.
- `GET /healthz` / `GET /readyz` – health probes for container orchestration.
- `GET /version`, `GET /api/version` and `GET /info` – build metadata and versioning details.

### 2.5 Frontend Experience
- Static HTML/vanilla JavaScript application served by FastAPI under `/`.
- Fetches `/api/markets/top?limit=20&vs=usd` on load, renders a sortable table and highlights CoinGecko categories as badges.
- Uses `/api/diag` to show a banner when the CoinGecko demo plan is active and to display refresh metadata.
- Provides retry affordance after network failures and surfaces the data source (API vs seed) to help operators detect stale information.

### 2.6 Asset Intelligence Coverage
- **Market intelligence & scores**: Score total dynamique (global aggregated score), score fondamental (news/ETF/regulation outlook) and detailed market overview (price, dominance, market cap, supply, volume, 24 h change). Categories and themes are exposed as badges to help users navigate comparable assets.
- **Communauté & sentiment**: Abonnés Twitter, Telegram members, Reddit subscribers, Discord population, newsletter reach and Google Trends alerts deliver a consolidated community health view.
- **Liquidité & DeFi depth**: Total Value Locked (TVL) trends, protocol dominance, exchange coverage, liquidity score, order book depth and fiat/stablecoin on-ramps surface how easy it is to enter/exit a position.
- **Opportunité & momentum**: RSI 14 j, volume acceleration, breakout detection, volatility regimes, whale transactions and funding rate shifts indicate tactical opportunities.
- **Sécurité & technologie**: Audit records, bug bounty programmes, incident history, GitHub commits/contributors/releases and infrastructure redundancy provide a trust profile.
- **Tokenomics & distribution**: Emission schedule, inflation, burn rate, staking ratio, unlock calendar, treasury allocation visibility and whale concentration describe supply dynamics.

## 3. Non-Functional Requirements
- **Performance**: respond to top-``N`` market requests within 200 ms on commodity hardware; ETL completes within the configured refresh interval.
- **Reliability**: seed fallback keeps the dashboard usable during upstream outages; persisted call budget prevents quota exhaustion.
- **Security**: HTTPS in production, masked API keys in logs, environment variables stripped of empty values.
- **Operability**: structured logging for outbound HTTP requests, diagnostics endpoint exposing runtime configuration, health endpoints for container orchestrators.

## 4. Data Flow & Background Processing
1. FastAPI startup configures logging, initialises the call budget and creates tables.
2. Startup ETL fetches markets; on failure the application loads the bundled seed fallback.
3. A background `asyncio` task reruns the ETL every `REFRESH_GRANULARITY` and records metadata (`last_refresh_at`, `last_etl_items`, `data_source`).
4. Latest prices are upserted for quick access while historical prices are appended for long-term analysis.
5. Category data is refreshed when stale and cached locally to limit CoinGecko calls.
6. Diagnostics endpoint combines persisted metadata and budget state to expose operational insights.

## 5. System Architecture
| Component | Responsibility |
|-----------|----------------|
| FastAPI application | Hosts REST API, diagnostics, health probes and static assets. |
| ETL runner | Fetches CoinGecko markets, categories and persists snapshots. |
| Persistence layer | SQLAlchemy models backed by SQLite (configurable via `DATABASE_URL`). |
| Call budget service | JSON-backed counter enforcing `CG_MONTHLY_QUOTA` and surfacing usage in `/api/diag`. |
| Frontend dashboard | Vanilla JavaScript + HTML table consuming the API. |

## 6. Technology Stack
| Layer | Technology |
|-------|------------|
| Backend | Python 3.11, FastAPI, SQLAlchemy, Pydantic Settings |
| Data fetching | Requests, Retry-enabled HTTP adapter |
| Database | SQLite by default (PostgreSQL planned) |
| Frontend | Static HTML, vanilla JavaScript, Fetch API |
| Testing | Pytest for backend, Jest-style assertions with Node for frontend utilities |
| DevOps | Docker, Docker Compose, GitHub Actions |

## 7. Roadmap

### Proof of Concept (delivered)
- [x] Liquidity and Opportunity scoring with global aggregation.
- [x] CoinGecko ETL with persisted snapshots, cached categories and seed fallback.
- [x] REST API for markets, price detail, categories, diagnostics, health and version.
- [x] Static dashboard delivered by the backend.
- [x] Docker Compose deployment pipeline for backend + frontend.

### Minimum Viable Product (planned)
- [ ] Add Community, Security, Technology and Tokenomics scores.
- [ ] Detect 100 trending assets outside the top 1,000.
- [ ] Migrate persistence to PostgreSQL and introduce background workers.
- [ ] Provide charts and configurable weighting controls on the frontend.
- [ ] Strengthen observability and automated alerting for ETL freshness.

### Engineering Validation Test (future)
- **Market intelligence & scores**
  - [ ] Score total dynamique consolidating thematic KPIs into a dynamic asset scorecard.
  - [ ] Score fondamental combining curated news, ETF coverage and macro sentiment tracking.
  - [ ] Automated category explorer linking comparable tokens by use case and sector.
- **Community analytics & sentiment**
  - [ ] Abonnés Twitter, Telegram, Reddit, Discord and YouTube dashboards with alert thresholds.
  - [ ] Google Trends, media coverage and influencer tracking for community momentum.
  - [ ] Newsletter performance and engagement scoring per asset.
- **Liquidity & DeFi depth**
  - [ ] Total Value Locked (TVL) history with protocol granularity and dominance ratios.
  - [ ] Order book depth analytics, exchange quality scoring and fiat/stablecoin on-ramps visibility.
  - [ ] Capital flow monitors for exchange inflow/outflow, stablecoin share and DeFi lock-up tracking.
- **Opportunité & trading signals**
  - [ ] RSI 14 j, breakout detection, volatility regime classification and funding rate direction.
  - [ ] Volume acceleration, whale transaction alerts and derivative open-interest monitors.
  - [ ] Seasonality, correlation clusters and relative strength versus benchmark indices.
- **Sécurité & technologie**
  - [ ] Audit registry integration, bug bounty coverage and incident response tracking.
  - [ ] GitHub velocity (commits, contributors, releases) and code quality indicators.
  - [ ] Node distribution, infrastructure redundancy and compliance controls.
- **Tokenomics & supply distribution**
  - [ ] Unlock and vesting calendar with impact scoring and alerts.
  - [ ] Inflation, burn schedule, staking ratio and yield analytics.
  - [ ] Treasury allocation visibility, whale concentration and token distribution monitoring.

## 8. Operational Guidelines
- Configure `BUDGET_FILE` so the CoinGecko call budget survives restarts; diagnostics display both persisted and in-memory counts.
- Avoid leaving environment variables empty—blank values are treated as unset and defaults kick in.
- Monitor `/api/diag` for `stale=true` to detect ETL issues and intervene before the dashboard lags behind.
- Use `/healthz` for liveness probes and `/readyz` for readiness checks in Docker/Kubernetes deployments.

## 9. Future Enhancements
- Replace SQLite with PostgreSQL and introduce Alembic migrations for schema evolution.
- Extend frontend with charts, filtering and internationalisation.
- Integrate additional data sources (Twitter, GitHub, on-chain metrics) once API quotas are validated.
- Add automated anomaly detection and alerting around ETL freshness and budget consumption.
