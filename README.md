# Tokenlysis

Tokenlysis is a FastAPI-based cryptocurrency ranking proof of concept. It ingests a configurable top ``N`` assets (1000 by default) from CoinGecko, stores the latest snapshots, multi-range historical prices and sentiment metrics in SQLite, and serves an interactive multi-page dashboard written in vanilla JavaScript with ApexCharts. Operators can monitor market breadth, open detailed asset views and track the Crypto Fear & Greed index without leaving the bundle.

> ⚠️ **Proprietary Notice**  
> This project is the proprietary software of **Tokenlysis**.  
> It is **not open source**.  
> You may view or fork the repository for **personal and non-commercial evaluation purposes only**.  
> Any commercial use, redistribution, or modification requires prior written permission from Tokenlysis.

The long-term roadmap is to analyse more than 1,000 assets with additional thematic categories and richer analytics. The [functional specifications](Functional_specs.md) capture the full target scope and future milestones.

## Current Capabilities

- **Universe** – configurable top ``N`` assets (default 1000) fetched from CoinGecko with logos and slugged categories cached server-side.
- **Scores & analytics** – Liquidity, Opportunity and a derived Global score computed from CoinGecko market data, persisted for historical comparisons and surfaced through dashboard gauges.
- **Historical prices** – `/api/price/{coin_id}/history` exposes 24h, 7d, 1m, 3m, 1y, 2y, 5y and full-range series that feed coin detail charts and the market overview.
- **Market overview** – aggregated market capitalisation and volume cards with 24h/7d deltas plus a top-market chart rendered from cached history.
- **Sentiment** – Crypto Fear & Greed index seeded from bundled history, refreshed via the CoinMarketCap API and rendered as a gauge with daily/weekly/monthly snapshots.
- **Refresh cadence** – background ETL runs every 12 hours (configurable with `REFRESH_GRANULARITY`).
- **Persistence** – SQLite keeps the latest market snapshot (`latest_prices`), historical snapshots (`prices`), sentiment entries (`fear_greed`) and service metadata (`meta`).
- **Frontend** – accessible vanilla JavaScript + ApexCharts bundle with retry handling, category badges (including overflow counters), light/dark theming and dedicated coin/sentiment pages.
- **Seed fallback** – when live data is unavailable the startup sequence loads a bundled seed fallback (`backend/app/seed/top20.json`) if `USE_SEED_ON_FAILURE` is enabled.
- **CoinGecko budget** – optional persisted call counter throttles requests according to `CG_MONTHLY_QUOTA` and surfaces monthly usage in diagnostics.

### API Surface

| Endpoint | Description |
| -------- | ----------- |
| `GET /api/markets/top` | Latest market snapshots limited to ``limit`` (clamped to ``[1, CG_TOP_N]``) for the `usd` quote. |
| `GET /api/price/{coin_id}` | Latest market snapshot for a single asset or `404` when unknown. |
| `GET /api/price/{coin_id}/history` | Historical price, market cap and volume series for the requested `range` (`24h`, `7d`, `1m`, `3m`, `1y`, `2y`, `5y`, `max`). |
| `GET /api/coins/{coin_id}/categories` | Cached CoinGecko category names and identifiers for an asset. |
| `GET /api/fng/latest` | Most recent Crypto Fear & Greed datapoint (score + label) with automatic historical fallback. |
| `GET /api/fng/history` | Historical scores sorted by timestamp, optionally filtered by `days` (e.g. 30, 90). |
| `GET /api/diag` | Operational diagnostics: CoinGecko plan, effective base URL, refresh interval, last ETL metadata, coin quota usage and data source. |
| `GET /api/last-refresh` | Shortcut exposing the most recent ETL timestamp. |
| `GET /healthz` / `GET /readyz` | Liveness and readiness endpoints used by container health checks. |
| `GET /version` / `GET /api/version` | Semantic build/version string sourced from `APP_VERSION` or Git metadata. |
| `GET /info` | Build metadata (version, git commit and build timestamp) for troubleshooting. |

### Frontend Dashboard

- Multi-page static bundle served from ``/`` by FastAPI (dashboard, coin detail and sentiment views) written in modular vanilla JavaScript with ApexCharts.
- Dashboard fetches `/api/markets/top?limit=1000&vs=usd`, renders hero summary cards (market cap & volume with 24h/7d deltas), a top-market chart with range selector and a sortable table enriched with coin logos.
- Category badges include overflow counters beyond three entries and link to dedicated asset pages (`coin.html?coin_id=...`).
- Coin detail view merges `/api/price/{coin_id}` and `/api/price/{coin_id}/history` to display price, market cap and volume charts with accessible `24h` → `max` range selectors and empty-state messaging.
- Fear & Greed view combines the latest/history endpoints, draws the gauge, renders snapshots for today/yesterday/week/month and plots sentiment history over `30d`, `90d`, `1y` or the full range.
- Theme toggle persists the preferred mode, `/api/diag` drives the demo-plan banner and the status bar surfaces retry actions plus last-refresh metadata when the API is unreachable.

## Asset Intelligence Reference

The reference dashboard shared for Tokenlysis highlights the information that must be surfaced for every cryptocurrency, even if the final UI differs from the mock-up. The current coin detail view already charts price, market cap, volume and categories as stepping stones towards that vision. Each asset view aggregates the following insights:

### Market intelligence & scores
- Score total dynamique combining daily refreshed thematic KPIs into a single gauge.
- Score fondamental emphasising news, ETF/regulation events and Google Trends momentum.
- Market overview cards for spot price, dominance, market capitalisation, volume, supply and 24 h change.
- Categories and themes surfaced as badges so users can explore comparable assets rapidly.

### Communauté & sentiment
- Abonnés Twitter, Telegram members, Reddit subscribers and Discord population updated daily.
- YouTube audience growth, newsletter reach and community engagement rate evolution.
- Google Trends watchlist per asset with alerts on breakout interest.

### Liquidité & DeFi depth
- Total Value Locked (TVL) trendlines and protocol breakdowns alongside on-chain dominance.
- Exchange coverage including trading pairs, liquidity score, order book depth and fiat on-ramp availability.

### Opportunité & momentum
- RSI 14 j, volume acceleration, breakout detection and volatility clustering signals.
- Whale transaction monitoring, funding rate shifts and seasonality versus Bitcoin/Ethereum benchmarks.

### Sécurité & technologie
- Audit coverage, bug bounty programmes, insurance partnerships and incident history.
- GitHub activity heatmaps (commits, contributors, releases) and infrastructure redundancy indicators.

### Tokenomics & distribution
- Emission schedule, inflation rate, burn events and staking ratio tracking.
- Unlock calendar, treasury allocation transparency and whale concentration metrics.

## ETL & Data Management

1. Resolve configuration (CoinGecko base URL, throttle, API key, quota, persisted budget path).
2. Fetch market data via `CoinGeckoClient` with per-call throttling, demo-plan backoff and budget accounting.
3. Persist latest snapshots and append to the historical table within a single transaction so the API and charts stay in sync.
4. Refresh category assignments and coin metadata (name, symbol, logo URL) when the cached value is older than 24 hours, falling back to slugified names.
5. Update metadata (`last_refresh_at`, `last_etl_items`, `data_source`, `monthly_call_count`) so diagnostics can expose freshness and quota consumption.
6. Trigger `sync_fear_greed_index()` after market ingestion to keep the sentiment cache aligned with CoinMarketCap.
7. On network failures, raise `DataUnavailable` so the caller can trigger the seed fallback and mark the dataset as stale.

The ETL runs on startup and then loops in the background according to `REFRESH_GRANULARITY`. It shares a persisted budget (`BUDGET_FILE`) with the API so the diagnostic endpoint can show quota consumption.

## Scoring Model

The proof of concept ships with two computed categories and a derived global score:

### Liquidity
- Metrics: 24 h trading volume (45 %), market capitalization (35 %), exchange listings (20 %).
- Method: logarithmic scaling and percentile normalisation.

### Opportunity
- Metrics: 14-day RSI (60 %) and day-over-day volume change (40 %).
- Method: RSI values above 70 are inverted to reward oversold assets; volume change is normalised to a 0–100 scale.

### Global
- Simple average of available category scores (ignores missing components).

Roadmap categories (Community, Security, Technology, Tokenomics) remain part of the MVP backlog and are documented in the functional specifications.

## Architecture

1. **ETL runner** – Python task fetching CoinGecko markets, refreshing category metadata and writing to SQLite.
2. **API backend** – FastAPI application exposing public endpoints under `/api`, diagnostics, health probes and static assets under `/`.
3. **Persistence layer** – SQLAlchemy ORM models for coins, latest prices, historical prices and metadata.
4. **Frontend** – Static HTML/vanilla JS dashboards (market overview, coin detail, sentiment) bundled inside the repository and served by FastAPI with ApexCharts.
5. **Call budget service** – Optional JSON-backed counter used to enforce the CoinGecko monthly quota and surface usage in diagnostics.
6. **Logging** – Structured JSON logs for outbound CoinGecko calls and contextual logs for ETL execution paths.
7. **Sentiment synchroniser** – CoinMarketCap client invoked after each ETL run to refresh Crypto Fear & Greed values consumed by the API and dashboards.

## Development Phases

### Proof of Concept (delivered)
- [x] Liquidity and Opportunity scoring with global aggregation.
- [x] CoinGecko ETL with persisted snapshots, cached categories, logo ingestion and seed fallback.
- [x] REST API for markets, price detail, price history, categories, diagnostics, health and version endpoints.
- [x] Crypto Fear & Greed ingestion with latest/history endpoints feeding dashboard widgets.
- [x] Interactive dashboard bundle (hero metrics, top-market chart, sortable table, light/dark theming) served by the backend.
- [x] Dedicated coin detail view with category badges and historical price/market/volume charts.
- [x] Docker Compose setup for backend + frontend (deployable on Synology NAS).

### Minimum Viable Product (planned)
- [ ] Add Community, Security, Technology and Tokenomics scores.
- [ ] Detect 100 trending assets outside the top 1,000.
- [ ] Introduce persistent PostgreSQL storage and background workers for heavier jobs.
- [ ] Provide user-defined weighting UI, saved filters and CSV/JSON export from the dashboard.
- [ ] Extend frontend with watchlists, category filters and richer attribution drill-downs powered by new API query parameters.
- [ ] Improve observability and automated alerting around ETL freshness, sentiment sync drift and budget exhaustion.

### Engineering Validation Test (future)
- **Market intelligence & scores**
  - [ ] Score total dynamique consolidating every category into a dynamic asset scorecard.
  - [ ] Score fondamental with curated news timeline, ETF coverage and macro narrative tracking.
  - [ ] Automated category and theme explorer tying comparable assets together.
  - [ ] Scenario analysis and what-if weighting simulator combining macro drivers with Tokenlysis scores.
- **Community analytics & sentiment**
  - [ ] Abonnés Twitter, Telegram, Reddit, Discord and YouTube dashboards with alerting thresholds.
  - [ ] Google Trends and social sentiment overlay to capture community momentum shifts.
  - [ ] Newsletter, influencer and media coverage bench-marking per asset.
  - [ ] Real-time alerting on social breakouts with anomaly detection and localisation for key regions.
- **Liquidity & DeFi depth**
  - [ ] Total Value Locked (TVL) history with protocol granularity and dominance ratios.
  - [ ] Order book depth, exchange quality scoring and fiat/stablecoin on-ramp visibility.
  - [ ] Capital flow indicators such as exchange inflow/outflow, stablecoin share and DeFi lock-up tracking.
  - [ ] Cross-exchange order book consolidation with slippage simulation and on-chain flow overlays.
- **Opportunité & trading signals**
  - [ ] RSI 14 j, breakout detection, volatility regime classification and funding rate direction.
  - [ ] Volume acceleration, whale transaction alerts and derivative open-interest monitors.
  - [ ] Seasonal performance, correlation clusters and relative strength versus benchmarks.
  - [ ] Backtesting playground to validate strategies and push signals to external alerting channels.
- **Sécurité & technologie**
  - [ ] Audit registry integration, bug bounty coverage and incident response tracking.
  - [ ] GitHub velocity metrics (commits, contributors, releases) with quality scoring.
  - [ ] Node distribution, infrastructure redundancy and compliance controls.
  - [ ] Supply-chain risk scoring covering dependencies on oracles, custodians and validators.
- **Tokenomics & supply distribution**
  - [ ] Unlock and vesting calendar with alerting and impact scoring.
  - [ ] Inflation, burn schedule, staking ratio and yield analytics.
  - [ ] Treasury allocation visibility, whale concentration and token distribution monitoring.
  - [ ] Treasury performance dashboard tracking historical allocations versus market moves and governance outcomes.

## Development

### Requirements

- Python 3.11+
- Install backend dependencies:
  ```bash
  pip install -r backend/requirements.txt
  ```

### Running Locally

```bash
uvicorn backend.app.main:app --reload
```

The frontend is served statically under `/` while REST endpoints are available under `/api`.

Set `APP_VERSION` when launching locally so the interface displays the expected version:

```bash
APP_VERSION=1.2.3 uvicorn backend.app.main:app --reload
```

When `APP_VERSION` is not set (or equals `dev`), the backend falls back to reading a `VERSION` file located next to the backend
sources. You can point to a custom location by exporting `VERSION_FILE` before starting the API.

### Configuration

Copy `.env.example` to `.env` and adjust the values as needed. The file contains sensitive settings such as API keys and database credentials; keep it outside version control and restrict access on your NAS (for example with `chmod 600 .env`).

Runtime behaviour can be tweaked with environment variables:

- `CORS_ORIGINS` – comma-separated list of allowed origins (default: `http://localhost`).
- `CG_TOP_N` – number of assets fetched from CoinGecko (default: `1000`).
- `CG_DAYS` – number of days of history to retrieve (default: `14`).
- `CG_MONTHLY_QUOTA` – maximum CoinGecko API calls per month (default: `10000`).
- `CG_PER_PAGE_MAX` – preferred page size for `/coins/markets` calls (default: `250`).
- `CG_ALERT_THRESHOLD` – fraction of the monthly quota that triggers a scope reduction (default: `0.7`).
- `CG_THROTTLE_MS` – minimum delay in milliseconds between CoinGecko API calls (default: `150`, raised to 2100 for the demo plan).
- `REFRESH_GRANULARITY` – cron-like hint exposed by `/api/diag` (default: `12h`); changing this value updates the ETL loop without restarting the app.
- `COINGECKO_BASE_URL` – override for the CoinGecko API endpoint (defaults to the public or pro URL based on `COINGECKO_PLAN`).
- `COINGECKO_API_KEY` / `coingecko_api_key` – optional API key for CoinGecko.
- `COINGECKO_PLAN` – `demo` (default) or `pro` to select the API header name.
- `CMC_API_KEY` – CoinMarketCap API key used to refresh the Crypto Fear & Greed index (optional).
- `CMC_BASE_URL` – override for the CoinMarketCap API endpoint (default: `https://pro-api.coinmarketcap.com`).
- `CMC_THROTTLE_MS` – minimum delay in milliseconds between CoinMarketCap requests (default: `1000`).
- `CMC_MONTHLY_QUOTA` – maximum CoinMarketCap Fear & Greed API calls per month (default: `3000`).
- `CMC_ALERT_THRESHOLD` – fraction of the CoinMarketCap quota that triggers an alert (default: `0.7`).
- `CMC_BUDGET_FILE` – path to the persisted CoinMarketCap call budget JSON file.
- `BUDGET_FILE` – path to the persisted CoinGecko call budget JSON file.
- `DATABASE_URL` – SQLAlchemy database URL (defaults to `sqlite:///./tokenlysis.db`).
- `USE_SEED_ON_FAILURE` – fall back to the bundled seed data when live ETL fails (default: `true`).
- `SEED_FILE` – path to the seed data used when `USE_SEED_ON_FAILURE` is enabled (default: `./backend/app/seed/top20.json`).
- `VERSION_FILE` – path to the file containing the build version when `APP_VERSION` is unset or equals `dev` (default: `./backend/VERSION`).
- `LOG_LEVEL` – base logging level for application and Uvicorn loggers (default: `INFO`). Accepts an integer or one of `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`, `FATAL`, `NOTSET`. Unknown values fall back to `INFO` with a warning. Use `UVICORN_LOG_LEVEL` or `--log-level` to override the server log level separately.
- `STATIC_ROOT` – absolute or repository-relative path to the directory containing the static frontend assets. By default FastAPI resolves `backend/app/main.py` two levels up to serve `frontend/`, which means you can start Uvicorn from any working directory. Override this when a deployment copies the assets elsewhere (for example to `/opt/tokenlysis/assets-statiques`).

#### Persistence (NAS)

When deploying on a Synology NAS, mount persistent volumes so the database and budget survive container restarts:

```
/volume1/docker/tokenlysis/data ↔ /data
```

The `.env.example` illustrates the host paths to persist data:

- `DATABASE_URL=sqlite:////volume1/docker/tokenlysis/data/tokenlysis.db`
- `BUDGET_FILE=/volume1/docker/tokenlysis/data/budget.json`

Ensure the container user has write permissions on the host directories.

Do **not** define environment variables with empty values. If a value is not needed, remove the variable or comment it out in `.env`. On Synology, delete the variable from the UI instead of leaving the field blank. Quotes around values (e.g. `LOG_LEVEL="INFO"`) are ignored. Boolean variables accept `true/false/1/0/yes/no/on/off` (case-insensitive, surrounding whitespace allowed). Empty or unrecognised values fall back to their defaults. Integer variables behave similarly: empty strings use the default and invalid numbers raise an explicit error.

The ETL fetches market data using CoinGecko coin IDs. During development the seed assets (`C1`, `C2`, …) are mapped to real CoinGecko IDs through `backend/app/config/seed_mapping.py`.

### Deployment on Synology NAS (POC)

1. **Install Container Manager** – from the Synology Package Center install the *Container Manager* application (formerly *Docker*).
2. **Clone the project** – obtain the Tokenlysis repository on your NAS:
   ```bash
   git clone https://github.com/Tomp0uce/Tokenlysis.git
   cd Tokenlysis
   cp .env.example .env
   chmod 600 .env
   ```
3. **Create the project** – in **Container Manager**, go to **Project → Create** and select `docker-compose.yml`. Add `docker-compose.synology.yml` as an override so the image is built locally. When defining environment variables in the Synology UI, never leave a value empty. If you do not have a value, remove the variable instead of leaving it blank. Supported boolean values are `true`, `false`, `1`, `0`, `yes`, `no`, `on` and `off` (case-insensitive); an empty value is treated as unset and defaults are applied.
4. **Build and start** – from the NAS terminal run:
   ```bash
   APP_VERSION=1.0.123 \
   docker compose -f docker-compose.yml -f docker-compose.synology.yml build --no-cache
   docker compose -f docker-compose.yml -f docker-compose.synology.yml up -d
   ```
   The build step injects the desired version into the image (defaults to `dev`). The subsequent `up` starts the container. A healthcheck inside the container polls `http://localhost:8000/readyz` every 30 seconds.
5. **Access the app** – the interface is available at `http://<NAS_IP>:8002` once the container reports healthy.

#### Updating

To update with a pinned version:
```bash
APP_VERSION=1.0.123 \
docker compose -f docker-compose.yml -f docker-compose.synology.yml build --no-cache
docker compose -f docker-compose.yml -f docker-compose.synology.yml up -d
```

## Testing

```bash
pytest
node --test tests/*.js
```

## Image Versioning

Docker images embed a version string that defaults to the number of commits in the repository. The value is passed at build time through the `APP_VERSION` build argument and exposed inside the container as the `APP_VERSION` environment variable. The same value is also written to the `org.opencontainers.image.version` OCI label for traceability.

GitHub Actions sets the value to `1.0.<run_number>` using `github.run_number` and injects it with `--build-arg APP_VERSION=${APP_VERSION}` during the build. When building locally you can override the version:

```bash
docker build --build-arg APP_VERSION=42 -t tokenlysis:test -f ./Dockerfile .
```

To propagate a new version to the dashboard and API, rebuild the image with the desired value:

```bash
APP_VERSION=1.2.3 \
docker compose -f docker-compose.yml -f docker-compose.synology.yml build --no-cache
docker compose -f docker-compose.yml -f docker-compose.synology.yml up -d
```

At runtime the container exposes `APP_VERSION` so it can be inspected with `docker run --rm tokenlysis:test env | grep APP_VERSION`. During the build the same value is written to `frontend/app-version.js` so the static dashboard can display the version even if the API is unreachable.

## License

This project is distributed under a proprietary license. See [LICENSE](LICENSE) for full terms and permitted usage.
