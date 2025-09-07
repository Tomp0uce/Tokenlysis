# Tokenlysis

Tokenlysis is a cryptocurrency scoring platform. The current proof of concept fetches a configurable top ``N`` assets (20 by default) from CoinGecko, computes **Liquidity** and **Opportunity** scores and aggregates them into a global score refreshed daily.

The long‑term goal is to rank more than 1,000 crypto-assets and highlight 100 trending tokens outside the top market-cap list. Additional categories and features will arrive in the MVP phase.

For a full overview of features and architecture, see the [functional specifications](Functional_specs.md).

## Overview

- **Universe**: configurable top ``N`` assets (default 20) from CoinGecko *(MVP: top 1000 + 100 trending)*.
- **Update schedule**: data is refreshed every day at 00:00 UTC.
- **Scores**: Liquidity, Opportunity and Global *(MVP: six categories: Community, Liquidity, Opportunity, Security, Technology, Tokenomics).* 

### Status

| Feature | Implemented | Planned |
| ------- | ----------- | ------- |
| Configurable top N (default 20) | ✅ | Top 1000 + 100 trending |
| Liquidity & Opportunity scores + Global | ✅ | Six categories with custom weights |
| Daily refresh aligned to 00:00 UTC | ✅ | DB + daily snapshots |
| Static frontend table | ✅ | Rich charts & filtering |
| `/api/version` endpoint | ✅ | Auth & watchlists |
| Seed fallback controlled by `USE_SEED_ON_FAILURE` | ✅ | Quotas & rate limiting |

## Scoring Model

### Liquidity
- Metrics: 24h trading volume (45%), market capitalization (35%), exchange listings (20%).
- Method: logarithmic scaling and percentile normalization.

### Opportunity
- Metrics: 14‑day RSI (60%) and day‑over‑day volume change (40%).
- Method: RSI inverted above 70 to reward oversold assets; volume change normalized on a 0‑100 scale.

### Community
- Metrics: Twitter followers (50%), 30‑day follower growth (30%), combined Discord/Reddit activity (20%).

### Security
- Metrics: number of completed audits (50%), network decentralization (30%), days since last major incident (20%).

### Technology
- Metrics: commits over the last 3 months (60%), active contributors (40%).

### Tokenomics
- Metrics: supply distribution (40%), inflation rate (30%), vesting/unlock schedule (30%).

## Development Phases

### POC
- [x] Liquidity scoring
- [x] Opportunity scoring
- [x] Global score aggregation
- [x] Mock ETL generating sample data
- [x] REST API for `/ranking`, `/asset/{id}` and `/history/{id}`
- [x] Static frontend table served by the backend
- [x] Docker Compose setup for backend and frontend (deployable on Synology NAS)

### MVP
- [ ] Community scoring
- [ ] Security scoring
- [ ] Technology scoring
- [ ] Tokenomics scoring
- [ ] Trending asset detection
- [ ] Persistent PostgreSQL storage
- [ ] User-defined weighting UI
- [ ] Interactive charts and comparisons

### EVT
- [ ] User accounts, authentication and watchlists
- [ ] Worker queue, caching layer and API rate limiting
- [ ] Historical score charts with price overlays and CSV export
- [ ] CI/CD pipeline with staging environment
- [ ] 80 %+ test coverage and load testing

## Architecture

1. **ETL** – Python scripts pull data from external APIs and compute daily metrics and scores.
2. **API** – A FastAPI application serves the scores and historical series.
3. **Frontend** – A minimal HTML/JS client displays a table of assets. Future versions will add filtering and charts.

## Development

### Requirements

- Python 3.11+
- Install dependencies:
  ```bash
  pip install -r backend/requirements.txt
  ```

### Running

```bash
uvicorn backend.app.main:app --reload
```

The frontend is served statically by the API under `/` while the REST endpoints
are exposed under `/api`.

#### Configuration

Copy `.env.example` to `.env` and adjust the values as needed. This file holds sensitive settings such as API keys and database passwords. Keep it outside version control (it is ignored by `.gitignore`) and restrict access on your NAS, for example with `chmod 600 .env`.
Runtime behaviour can be tweaked with environment variables:

- `CORS_ORIGINS` – comma-separated list of allowed origins (default:
  `http://localhost`)
- `CG_TOP_N` – number of assets fetched from CoinGecko (default: `20`)
- `CG_DAYS` – number of days of history to retrieve (default: `14`)
- `COINGECKO_API_KEY` – optional API key for the CoinGecko Pro plan
- `USE_SEED_ON_FAILURE` – fall back to bundled seed data when live ETL fails (default: `false`)
- `LOG_LEVEL` – base logging level for application and Uvicorn loggers (default: `INFO`).
  Accepts an integer or one of
  `DEBUG`, `INFO`, `WARN`, `WARNING`, `ERROR`, `CRITICAL`, `FATAL` or `NOTSET`.
  Unknown values fall back to `INFO` with a warning. Use `UVICORN_LOG_LEVEL` or
  `--log-level` to override server log level separately.

Do **not** define environment variables with empty values. If a value is not
needed, remove the variable or comment it out in `.env`. On Synology, delete the
variable from the UI instead of leaving the field blank. Quotes around values
(e.g. `LOG_LEVEL="INFO"`) are ignored.

Boolean variables accept `true/false/1/0/yes/no/on/off` (case-insensitive, surrounding
whitespace allowed). Empty or unrecognised values fall back to their defaults.
Integer variables behave similarly: empty strings use the default and invalid numbers
raise an explicit error.

The ETL fetches market data using CoinGecko's coin IDs. During development the
seed assets (`C1`, `C2`, …) are mapped to real CoinGecko IDs through
`backend/app/config/seed_mapping.py`.

### Health & Diagnostics

- `GET /healthz` – basic liveness probe
- `GET /readyz` – readiness check querying CoinGecko
- `GET /api/diag` – returns app version, outbound status and masked API key

### Synology NAS Deployment (POC)

The following steps describe how to deploy Tokenlysis on a Synology NAS using
the local source code.

1. **Install Container Manager** – from the Synology Package Center install the
   *Container Manager* application (formerly called *Docker*).
2. **Clone the project** – obtain the Tokenlysis repository on your NAS, e.g.:

   ```bash
   git clone https://github.com/Tomp0uce/Tokenlysis.git
   cd Tokenlysis
   ```

   Create a `.env` file from the example and secure it on the NAS:

   ```bash
   cp .env.example .env
   chmod 600 .env
   ```

3. **Create the project** – in **Container Manager**, go to **Project** →
   **Create** and select the `docker-compose.yml` file from the cloned folder.
   Add `docker-compose.synology.yml` as an additional compose file so the image
   is built locally. When defining environment variables in the Synology UI,
   never leave a value empty. If you don't have a value, remove the variable
   instead of leaving it blank. Supported boolean values are `true`, `false`,
   `1`, `0`, `yes`, `no`, `on` and `off` (case-insensitive); an empty value is
   treated as unset and defaults are applied.
4. **Build and start** – from the NAS terminal run:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.synology.yml up -d --build
   ```

   This builds the image with the main `Dockerfile` and forwards an optional
   `APP_VERSION` build argument. Define `APP_VERSION` to pin a specific version
   or let it default to `dev`.
   A healthcheck inside the container polls `http://localhost:8000/readyz` every 30 seconds.
5. **Access the app** – once running the interface is available at
   `http://<NAS_IP>:8002`.

#### Updating

When new commits are pushed to the repository you can rebuild the container to
fetch the latest code. Either use the Synology UI’s **Recreate** option or run:

```bash
docker compose -f docker-compose.yml -f docker-compose.synology.yml up -d --build
```

The `--build` flag forces Compose to rebuild the image, ensuring the container
runs the newest version of Tokenlysis.

### Testing

```bash
pytest
```

### Image Version

Docker images embed a version string that defaults to the number of commits in
the repository. The value is passed at build time through the `APP_VERSION`
build argument and is exposed inside the container as the `APP_VERSION`
environment variable. The same value is also written to the
`org.opencontainers.image.version` OCI label for traceability.

GitHub Actions computes the value with `git rev-list --count HEAD` and injects it
with `--build-arg APP_VERSION=${APP_VERSION_SHORT}` during the build. When
building locally you can override the version:

```bash
docker build --build-arg APP_VERSION=42 -t tokenlysis:test -f ./Dockerfile .
```

At runtime the container exposes `APP_VERSION` so it can be inspected with
`docker run --rm tokenlysis:test env | grep APP_VERSION`.

## License

This project is licensed under the MIT License.

