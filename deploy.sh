#!/bin/bash
set -e

ENV_DIR="/volume1/docker/tokenlysis/config"
REPO_DIR="/volume1/docker/tokenlysis/repo"

# Construit le .env à partir des secrets + variables publiques
cp "$ENV_DIR/.env.public" "$REPO_DIR/backend/.env" 2>/dev/null || true

if [ -f "$ENV_DIR/secrets/COINGECKO_API_KEY" ]; then
  echo "COINGECKO_API_KEY=$(cat $ENV_DIR/secrets/COINGECKO_API_KEY)" >> "$REPO_DIR/backend/.env"
fi
