# Tokenlysis

Tokenlysis is a cryptocurrency scoring platform that aggregates market, social and on-chain data for thousands of digital assets and computes a daily score for each one.

It ranks more than 1,000 crypto-assets and highlights 100 trending tokens outside the top market-cap list. Users can explore score history, compare assets and, in future releases, customise category weights to suit their strategy.

For a full overview of features and architecture, see the [functional specifications](Functional_specs.md).

## Overview

- **Universe**: top 1000 cryptocurrencies by market capitalization plus 100 emerging "trending" assets outside the top 1000, selected by 24h volume and social interest.
- **Update schedule**: data is refreshed every day at 00:00 UTC.
- **Scores**: each asset receives a global score from 0 to 100 and six category scores: Community, Liquidity, Opportunity, Security, Technology and Tokenomics. The global score is the weighted average of the categories.

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

Runtime behaviour can be tweaked with environment variables:

- `CORS_ORIGINS` – comma-separated list of allowed origins (default:
  `http://localhost`)
- `CG_TOP_N` – number of assets fetched from CoinGecko (default: `20`)
- `CG_DAYS` – number of days of history to retrieve (default: `14`)

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

3. **Create the project** – in **Container Manager**, go to **Project** →
   **Create** and select the `docker-compose.synology.yml` file from the cloned
   folder.
4. **Build and start** – from the NAS terminal or the Synology UI run:

   ```bash
   docker compose -f docker-compose.synology.yml up -d --build
   ```

   This builds the image with the main `Dockerfile` and forwards an optional
   `APP_VERSION` build argument. Define `APP_VERSION` to pin a specific version
   or let it default to `dev`.
5. **Access the app** – once running the interface is available at
   `http://<NAS_IP>:8002`.

#### Updating

When new commits are pushed to the repository you can rebuild the container to
fetch the latest code. Either use the Synology UI’s **Recreate** option or run:

```bash
docker compose -f docker-compose.synology.yml up -d --build
```

The `--build` flag forces Compose to pull the repository again and rebuild the
image, ensuring the container runs the newest version of Tokenlysis.

### Testing

```bash
pytest
```

### Image Version

Docker images embed a version string that defaults to the short Git commit SHA.
The value is passed at build time through the `APP_VERSION` build argument and is
exposed inside the container as the `APP_VERSION` environment variable. The same
value is also written to the `org.opencontainers.image.version` and
`org.opencontainers.image.revision` OCI labels for traceability.

GitHub Actions computes the value from `GITHUB_SHA` and injects it with
`--build-arg APP_VERSION=${APP_VERSION_SHORT}` during the build. When building
locally you can override the version:

```bash
docker build --build-arg APP_VERSION=abcdef1 -t tokenlysis:test -f ./Dockerfile .
```

At runtime the container exposes `APP_VERSION` so it can be inspected with
`docker run --rm tokenlysis:test env | grep APP_VERSION`.

## License

This project is licensed under the MIT License.

