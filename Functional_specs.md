# Functional Specifications

## 1. Project Overview
Tokenlysis is a public web platform that ranks a configurable top ``N`` cryptocurrencies using CoinGecko market data. The proof of concept focuses on the top 1000 assets by default, computes **Liquidity**, **Opportunity** and a derived **Global** score, and refreshes data every 12 hours through a background ETL loop. An interactive bundle built with vanilla JavaScript and ApexCharts consumes the public API to render market overview, coin detail and sentiment dashboards enriched with category badges and freshness indicators.

## 2. Current Functional Scope
### 2.1 Asset Universe & Data Freshness
- Configurable universe controlled by `CG_TOP_N` (default 1000) sourced from CoinGecko.
- Background ETL fetches markets on startup and then at the cadence defined by `REFRESH_GRANULARITY` (default 12 h).
- Fallback to bundled seed data when the live fetch fails and `USE_SEED_ON_FAILURE` is enabled.
- Coin metadata (name, symbol, logo URL) is cached alongside category payloads to enrich API responses and dashboards.

### 2.2 Scoring System
- **Liquidity** – Log-scaled normalisation of market cap, 24 h volume and exchange listings.
- **Opportunity** – Relative Strength Index (RSI) and day-over-day volume change, with RSI inverted above 70 to highlight oversold assets.
- **Global** – Mean of available category scores, ignoring missing components.
- Scores are persisted alongside market snapshots to power historical analysis in future iterations.
- Dashboard hero cards and radial gauges reuse the same scores to surface Liquidity/Opportunity/Global insights at a glance.

### 2.3 Category Management
- CoinGecko categories are cached per asset with a 24-hour freshness threshold.
- Categories are stored as JSON payloads in the `coins` table and exposed through `/api/coins/{coin_id}/categories` and the markets endpoint.
- Slugs derived from category names provide stable identifiers when CoinGecko lacks explicit IDs.
- Logo URLs are stored at the same time so the frontend can display coin branding without additional API hops.

### 2.4 Public API
- `GET /api/markets/top` – list latest market snapshots, clamping `limit` to `[1, CG_TOP_N]` and enforcing `vs=usd` (returns data source, last refresh timestamp and stale flag).
- `GET /api/price/{coin_id}` – retrieve a single asset snapshot or `404` when unavailable.
- `GET /api/price/{coin_id}/history` – provide price, market cap and volume time series for `range` in (`24h`, `7d`, `1m`, `3m`, `1y`, `2y`, `5y`, `max`).
- `GET /api/coins/{coin_id}/categories` – expose cached category names and IDs.
- `GET /api/diag` – diagnostics including CoinGecko plan, effective base URL, refresh interval, last ETL item count, persisted call budget, monthly call count and configured universe size.
- `GET /api/last-refresh` – lightweight endpoint returning only the last refresh timestamp.
- `GET /healthz` / `GET /readyz` – health probes for container orchestration.
- `GET /version`, `GET /api/version` and `GET /info` – build metadata and versioning details.

### 2.5 Frontend Experience
- Modular vanilla JavaScript bundle served by FastAPI under `/` with ApexCharts powering dashboard, coin and sentiment pages.
- Dashboard fetches `/api/markets/top?limit=1000&vs=usd`, renders hero summary cards (market cap & volume with 24h/7d deltas) and a top-market chart controlled by range selectors.
- The sortable ranking table displays coin logos, category badges with overflow counters and links each asset to its dedicated detail view.
- Coin detail pages merge `/api/price/{coin_id}` and `/api/price/{coin_id}/history` to show metrics plus price/market cap/volume charts with `24h` → `max` ranges and empty-state handling.
- The sentiment page consumes the Fear & Greed endpoints to draw a gauge, snapshots for today/yesterday/week/month and a history chart for `30d`, `90d`, `1y` or full-range windows.
- Theme toggle persists the preferred mode, `/api/diag` drives the demo-plan banner and retry/status messaging surfaces when network calls fail.

### 2.6 Asset Intelligence Coverage
The delivered dashboards already surface price, market cap, volume history and category badges within the coin detail view, establishing the baseline for the richer intelligence modules below.
- **Market intelligence & scores**: Score total dynamique (global aggregated score), score fondamental (news/ETF/regulation outlook) and detailed market overview (price, dominance, market cap, supply, volume, 24 h change). Categories and themes are exposed as badges to help users navigate comparable assets.
- **Communauté & sentiment**: Abonnés Twitter, Telegram members, Reddit subscribers, Discord population, newsletter reach and Google Trends alerts deliver a consolidated community health view.
- **Liquidité & DeFi depth**: Total Value Locked (TVL) trends, protocol dominance, exchange coverage, liquidity score, order book depth and fiat/stablecoin on-ramps surface how easy it is to enter/exit a position.
- **Opportunité & momentum**: RSI 14 j, volume acceleration, breakout detection, volatility regimes, whale transactions and funding rate shifts indicate tactical opportunities.
- **Sécurité & technologie**: Audit records, bug bounty programmes, incident history, GitHub commits/contributors/releases and infrastructure redundancy provide a trust profile.
- **Tokenomics & distribution**: Emission schedule, inflation, burn rate, staking ratio, unlock calendar, treasury allocation visibility and whale concentration describe supply dynamics.

### 2.7 Historical Analytics
- `/api/price/{coin_id}/history` serves price, market cap and volume points for configurable ranges (`24h`, `7d`, `1m`, `3m`, `1y`, `2y`, `5y`, `max`).
- Dashboard hero cards and the top-market chart reuse cached history to summarise aggregate capitalisation and volume trends.
- Coin detail charts share range selectors and empty-state messages to guarantee a consistent experience across assets with sparse data.

### 2.8 Sentiment Intelligence
- CoinMarketCap integration seeds and refreshes the Crypto Fear & Greed index, storing values in the `fear_greed` table.
- `/api/fng/latest` and `/api/fng/history` expose the dataset to frontend widgets, returning normalized `{ timestamp, score, label }` points with optional `days` filtering.
- A dedicated sentiment page renders the gauge, history chart and contextual legend while the dashboard hero card links directly to it.

### 2.9 Navigation & Theming
- Static bundle ships with `index.html`, `coin.html` and `fear-greed.html` routes backed by ES modules and ApexCharts.
- Theme toggle persists the preferred light/dark mode across sessions and updates chart palettes via a shared observer.
- Status banner surfaces retry controls, last-refresh metadata and demo-plan notices driven by `/api/markets/top` and `/api/diag` responses.

## 3. Non-Functional Requirements
- **Performance**: respond to top-``N`` market requests within 200 ms on commodity hardware; ETL completes within the configured refresh interval.
- **Reliability**: seed fallback keeps the dashboard usable during upstream outages; persisted call budget prevents quota exhaustion.
- **Security**: HTTPS in production, masked API keys in logs, environment variables stripped of empty values.
- **Operability**: structured logging for outbound HTTP requests, diagnostics endpoint exposing runtime configuration, health endpoints for container orchestrators.

## 4. Data Flow & Background Processing
1. FastAPI startup configures logging, initialises the call budget, mounts static assets and creates database tables.
2. Startup ETL fetches markets; on failure the application loads the bundled seed fallback.
3. A background `asyncio` task reruns the ETL every `REFRESH_GRANULARITY`, updating metadata (`last_refresh_at`, `last_etl_items`, `data_source`, `monthly_call_count`).
4. Latest prices are upserted for quick access while historical prices are appended for long-term analysis.
5. Category data, coin names, symbols and logo URLs are refreshed when stale and cached locally to limit CoinGecko calls.
6. Diagnostics endpoint combines persisted metadata and budget state to expose operational insights.
7. After each market ingestion, the CoinMarketCap client synchronises the Crypto Fear & Greed index so sentiment widgets stay fresh.

## 5. System Architecture
| Component | Responsibility |
|-----------|----------------|
| FastAPI application | Hosts REST API, diagnostics, health probes and static assets. |
| ETL runner | Fetches CoinGecko markets, categories and persists snapshots. |
| Persistence layer | SQLAlchemy models backed by SQLite (configurable via `DATABASE_URL`). |
| Call budget service | JSON-backed counter enforcing `CG_MONTHLY_QUOTA` and surfacing usage in `/api/diag`. |
| Sentiment synchroniser | CoinMarketCap integration refreshing Crypto Fear & Greed entries after each ETL cycle. |
| Frontend dashboard | Vanilla JavaScript + HTML/ApexCharts bundle consuming the API. |

## 6. Technology Stack
| Layer | Technology |
|-------|------------|
| Backend | Python 3.11, FastAPI, SQLAlchemy, Pydantic Settings |
| Data fetching | Requests, Retry-enabled HTTP adapter |
| Database | SQLite by default (PostgreSQL planned) |
| Frontend | Static HTML, vanilla JavaScript modules, ApexCharts, Fetch API |
| Testing | Pytest for backend, Node 20 `node --test` suites with jsdom for frontend utilities |
| DevOps | Docker, Docker Compose, GitHub Actions |

## 7. Roadmap

### Proof of Concept (delivered)
- [x] Liquidity and Opportunity scoring with global aggregation.
- [x] CoinGecko ETL with persisted snapshots, cached categories, logo ingestion and seed fallback.
- [x] REST API for markets, price detail, price history, categories, diagnostics, health and version endpoints.
- [x] Crypto Fear & Greed ingestion with latest/history endpoints powering dashboard widgets.
- [x] Interactive dashboard bundle (hero metrics, top-market chart, sortable table, light/dark theming) served by the backend.
- [x] Dedicated coin detail view with category badges and historical price/market/volume charts.
- [x] Docker Compose deployment pipeline for backend + frontend.

### Minimum Viable Product (planned)
- [ ] Add Community, Security, Technology and Tokenomics scores.
- [ ] Detect 100 trending assets outside the top 1,000.
- [ ] Migrate persistence to PostgreSQL and introduce background workers for heavier jobs.
- [ ] Provide user-defined weighting UI, saved filters and CSV/JSON export from the dashboard.
- [ ] Extend frontend with watchlists, category filters and richer attribution drill-downs powered by new API query parameters.
- [ ] Strengthen observability and automated alerting around ETL freshness, sentiment sync drift and budget exhaustion.

### Engineering Validation Test (future)
- **Market intelligence & scores**
  - [ ] Score total dynamique consolidating thematic KPIs into a dynamic asset scorecard.
  - [ ] Score fondamental combining curated news, ETF coverage and macro sentiment tracking.
  - [ ] Automated category explorer linking comparable tokens by use case and sector.
  - [ ] Scenario analysis and what-if weighting simulator combining macro drivers with Tokenlysis scores.
- **Community analytics & sentiment**
  - [ ] Abonnés Twitter, Telegram, Reddit, Discord and YouTube dashboards with alert thresholds.
  - [ ] Google Trends, media coverage and influencer tracking for community momentum.
  - [ ] Newsletter performance and engagement scoring per asset.
  - [ ] Real-time alerting on social breakouts with anomaly detection and localisation for key regions.
- **Liquidity & DeFi depth**
  - [ ] Total Value Locked (TVL) history with protocol granularity and dominance ratios.
  - [ ] Order book depth analytics, exchange quality scoring and fiat/stablecoin on-ramps visibility.
  - [ ] Capital flow monitors for exchange inflow/outflow, stablecoin share and DeFi lock-up tracking.
  - [ ] Cross-exchange order book consolidation with slippage simulation and on-chain flow overlays.
- **Opportunité & trading signals**
  - [ ] RSI 14 j, breakout detection, volatility regime classification and funding rate direction.
  - [ ] Volume acceleration, whale transaction alerts and derivative open-interest monitors.
  - [ ] Seasonality, correlation clusters and relative strength versus benchmark indices.
  - [ ] Backtesting playground to validate strategies and push signals to external alerting channels.
- **Sécurité & technologie**
  - [ ] Audit registry integration, bug bounty coverage and incident response tracking.
  - [ ] GitHub velocity (commits, contributors, releases) and code quality indicators.
  - [ ] Node distribution, infrastructure redundancy and compliance controls.
  - [ ] Supply-chain risk scoring covering dependencies on oracles, custodians and validators.
- **Tokenomics & supply distribution**
  - [ ] Unlock and vesting calendar with impact scoring and alerts.
  - [ ] Inflation, burn schedule, staking ratio and yield analytics.
  - [ ] Treasury allocation visibility, whale concentration and token distribution monitoring.
  - [ ] Treasury performance dashboard tracking historical allocations versus market moves and governance outcomes.

## 8. Operational Guidelines
- Configure `BUDGET_FILE` so the CoinGecko call budget survives restarts; diagnostics display both persisted and in-memory counts.
- Avoid leaving environment variables empty—blank values are treated as unset and defaults kick in.
- Monitor `/api/diag` for `stale=true` to detect ETL issues and intervene before the dashboard lags behind.
- Use `/healthz` for liveness probes and `/readyz` for readiness checks in Docker/Kubernetes deployments.

## 9. Future Enhancements
- Replace SQLite with PostgreSQL and introduce Alembic migrations for schema evolution.
- Extend frontend with workspace personalisation, multi-faceted filtering and internationalisation.
- Integrate additional data sources (Twitter, GitHub, on-chain metrics) once API quotas are validated to unlock Community/Security/Technology scoring.
- Add automated anomaly detection and alerting around ETL freshness, sentiment drift and budget consumption.
- Provide export APIs and webhooks so downstream systems can react to Tokenlysis rankings and sentiment changes in real time.
