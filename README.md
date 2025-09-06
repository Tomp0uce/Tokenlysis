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

The following steps describe how to deploy Tokenlysis on a Synology NAS and let
Docker Compose fetch the source code automatically.

1. **Install Container Manager** – from the Synology Package Center install the
   *Container Manager* application (formerly called *Docker*).
2. **Create a project** – open **Container Manager**, go to **Project** →
   **Create** → **Import from URL** and paste:

   ```text
   https://raw.githubusercontent.com/Tomp0uce/Tokenlysis/main/docker-compose.synology.yml
   ```

   This compose file contains a `build` section pointing directly to the Git
   repository so the code is downloaded during the first build.
3. **Confirm settings** – keep port `8000` exposed (or change if needed) and
   create the project. The initial `docker compose up` will clone the
   repository, build the image and start the container.
4. **Access the app** – once running the interface is available at
   `http://<NAS_IP>:8000`.

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

## License

This project is licensed under the MIT License.

