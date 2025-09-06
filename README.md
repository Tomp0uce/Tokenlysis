# Tokenlysis

Tokenlysis is a cryptocurrency scoring platform that aggregates market, social and on-chain data for thousands of digital assets and computes a daily score for each one.

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

## Feature Status

- [x] Liquidity scoring
- [x] Opportunity scoring
- [x] Global score aggregation
- [x] Mock ETL generating sample data
- [x] REST API for listing assets, details and history
- [x] Static frontend table
- [ ] Community scoring
- [ ] Security scoring
- [ ] Technology scoring
- [ ] Tokenomics scoring
- [ ] Trending asset detection
- [ ] Persistent database storage
- [ ] User‑defined weighting
- [ ] Interactive charts and comparisons

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

The frontend is served statically by the API under `/`.

### Testing

```bash
pytest
```

## License

This project is licensed under the MIT License.

