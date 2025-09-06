# Tokenlysis

Simple crypto analysis backend with a minimal front-end for testing.

## Running the API

```bash
uvicorn backend.app.main:app --reload
```

## Using the front-end

Open `frontend/index.html` in a browser once the API is running. It will fetch and
display the list of cryptocurrencies with their price and global score.
