# Tokenlysis

Tokenlysis is a FastAPI-based cryptocurrency ranking proof of concept. It ingests a configurable top ``N`` assets (50 by default) from CoinGecko, stores both the latest snapshot and historical prices in SQLite and serves a lightweight dashboard written in vanilla JavaScript.

> ⚠️ **Proprietary Notice**  
> This project is the proprietary software of **Tokenlysis**.  
> It is **not open source**.  
> You may view or fork the repository for **personal and non-commercial evaluation purposes only**.  
> Any commercial use, redistribution, or modification requires prior written permission from Tokenlysis.

The long-term roadmap is to analyse more than 1,000 assets with additional thematic categories and richer analytics. The [functional specifications](Functional_specs.md) capture the full target scope and future milestones.

## Current Capabilities

- **Universe** – configurable top ``N`` assets (default 50) fetched from CoinGecko.
- **Scores** – Liquidity, Opportunity and a derived Global score computed from CoinGecko market data.
- **Refresh cadence** – background ETL runs every 12 hours (configurable with `REFRESH_GRANULARITY`).
- **Persistence** – SQLite keeps the latest market snapshot (`latest_prices`), historical snapshots (`prices`) and service metadata (`meta`).
- **Categories** – CoinGecko categories are cached per asset and refreshed every 24 hours.
- **Sentiment** – Crypto Fear & Greed index seeded from bundled history and refreshed via the CoinMarketCap API.
- **Seed fallback** – when live data is unavailable the startup sequence loads a bundled seed fallback (`backend/app/seed/top20.json`) if `USE_SEED_ON_FAILURE` is enabled.
- **CoinGecko budget** – optional persisted call counter throttles requests according to `CG_MONTHLY_QUOTA`.

### API Surface

| Endpoint | Description |
| -------- | ----------- |
| `GET /api/markets/top` | Latest market snapshots limited to ``limit`` (clamped to ``[1, CG_TOP_N]``) for the `usd` quote. |
| `GET /api/price/{coin_id}` | Latest market snapshot for a single asset or `404` when unknown. |
| `GET /api/coins/{coin_id}/categories` | Cached CoinGecko category names and identifiers for an asset. |
| `GET /api/fear-greed/latest` | Most recent Crypto Fear & Greed datapoint with classification, or `404` when unavailable. |
| `GET /api/fear-greed/history` | Historical values filtered by `range` (`30d`, `90d`, `1y`, `max`). |
| `GET /api/diag` | Operational diagnostics: CoinGecko plan, effective base URL, refresh interval, last ETL metadata, coin quota usage and data source. |
| `GET /api/last-refresh` | Shortcut exposing the most recent ETL timestamp. |
| `GET /healthz` / `GET /readyz` | Liveness and readiness endpoints used by container health checks. |
| `GET /version` / `GET /api/version` | Semantic build/version string sourced from `APP_VERSION` or Git metadata. |
| `GET /info` | Build metadata (version, git commit and build timestamp) for troubleshooting. |

### Frontend Dashboard

- Static HTML + vanilla JavaScript served from ``/`` by FastAPI.
- Fetches `/api/markets/top?limit=20&vs=usd` on load and renders a sortable table.
- Displays CoinGecko categories as badges with overflow counters beyond three categories.
- Shows the daily Crypto Fear & Greed gauge linking to a dedicated sentiment page.
- Queries `/api/diag` to display a banner whenever the service runs on the CoinGecko demo plan.
- Includes a retry affordance on fetch errors and shows the last refresh timestamp and data source.
- A dedicated `fear-greed.html` view renders the gauge and historical chart with range selection (`30d`, `90d`, `1y`, `max`).

## Asset Intelligence Reference

The reference dashboard shared for Tokenlysis highlights the information that must be surfaced for every cryptocurrency, even if the final UI differs from the mock-up. Each asset view aggregates the following insights:

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

1. Resolve configuration (CoinGecko base URL, throttle, API key, quota).
2. Fetch market data via `CoinGeckoClient` with per-call throttling and retry handling.
3. Persist latest snapshots and append to the historical table within a single transaction.
4. Refresh category assignments when the cached value is older than 24 hours, falling back to cached slugs.
5. Update metadata (`last_refresh_at`, `last_etl_items`, `data_source`) and store the monthly call count when a budget file is configured.
6. On network failures, raise `DataUnavailable` so the caller can trigger the seed fallback and mark the dataset as stale.

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
4. **Frontend** – Static HTML/vanilla JS table bundled inside the repository and served by FastAPI.
5. **Call budget service** – Optional JSON-backed counter used to enforce the CoinGecko monthly quota and surface usage in diagnostics.
6. **Logging** – Structured JSON logs for outbound CoinGecko calls and contextual logs for ETL execution paths.

## Development Phases

### Proof of Concept (delivered)
- [x] Liquidity and Opportunity scoring with global aggregation.
- [x] CoinGecko ETL with persisted snapshots, cached categories and seed fallback.
- [x] REST API for markets, price detail, categories, diagnostics, health and version.
- [x] Static dashboard delivered by the backend.
- [x] Docker Compose setup for backend + frontend (deployable on Synology NAS).

### Minimum Viable Product (planned)
- [ ] Add Community, Security, Technology and Tokenomics scores.
- [ ] Detect 100 trending assets outside the top 1,000.
- [ ] Introduce persistent PostgreSQL storage and background workers for heavier jobs.
- [ ] Provide basic charts and user-defined weighting UI on the frontend.
- [ ] Improve observability and automated alerting around ETL freshness.

### Engineering Validation Test (future)
- **Market intelligence & scores**
  - [ ] Score total dynamique consolidating every category into a dynamic asset scorecard.
  - [ ] Score fondamental with curated news timeline, ETF coverage and macro narrative tracking.
  - [ ] Automated category and theme explorer tying comparable assets together.
- **Community analytics & sentiment**
  - [ ] Abonnés Twitter, Telegram, Reddit, Discord and YouTube dashboards with alerting thresholds.
  - [ ] Google Trends and social sentiment overlay to capture community momentum shifts.
  - [ ] Newsletter, influencer and media coverage bench-marking per asset.
- **Liquidity & DeFi depth**
  - [ ] Total Value Locked (TVL) history with protocol granularity and dominance ratios.
  - [ ] Order book depth, exchange quality scoring and fiat/stablecoin on-ramp visibility.
  - [ ] Capital flow indicators such as exchange inflow/outflow, stablecoin share and DeFi lock-up tracking.
- **Opportunité & trading signals**
  - [ ] RSI 14 j, breakout detection, volatility regime classification and funding rate direction.
  - [ ] Volume acceleration, whale transaction alerts and derivative open-interest monitors.
  - [ ] Seasonal performance, correlation clusters and relative strength versus benchmarks.
- **Sécurité & technologie**
  - [ ] Audit registry integration, bug bounty coverage and incident response tracking.
  - [ ] GitHub velocity metrics (commits, contributors, releases) with quality scoring.
  - [ ] Node distribution, infrastructure redundancy and compliance controls.
- **Tokenomics & supply distribution**
  - [ ] Unlock and vesting calendar with alerting and impact scoring.
  - [ ] Inflation, burn schedule, staking ratio and yield analytics.
  - [ ] Treasury allocation visibility, whale concentration and token distribution monitoring.

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

### Configuration

Copy `.env.example` to `.env` and adjust the values as needed. The file contains sensitive settings such as API keys and database credentials; keep it outside version control and restrict access on your NAS (for example with `chmod 600 .env`).

Runtime behaviour can be tweaked with environment variables:

- `CORS_ORIGINS` – comma-separated list of allowed origins (default: `http://localhost`).
- `CG_TOP_N` – number of assets fetched from CoinGecko (default: `50`).
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
- `FEAR_GREED_SEED_FILE` – path to the historical seed file for the Crypto Fear & Greed index (default: `./crypto_fear_greed_index_data.txt`).
- `BUDGET_FILE` – path to the persisted CoinGecko call budget JSON file.
- `DATABASE_URL` – SQLAlchemy database URL (defaults to `sqlite:///./tokenlysis.db`).
- `USE_SEED_ON_FAILURE` – fall back to the bundled seed data when live ETL fails (default: `true`).
- `SEED_FILE` – path to the seed data used when `USE_SEED_ON_FAILURE` is enabled (default: `./backend/app/seed/top20.json`).
- `LOG_LEVEL` – base logging level for application and Uvicorn loggers (default: `INFO`). Accepts an integer or one of `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`, `FATAL`, `NOTSET`. Unknown values fall back to `INFO` with a warning. Use `UVICORN_LOG_LEVEL` or `--log-level` to override the server log level separately.

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
