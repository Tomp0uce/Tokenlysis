#!/bin/sh
# Tokenlysis - Déploiement Synology (SQLite)
set -eu
(set -o pipefail) 2>/dev/null || true
umask 077

# --- Réglages ---
PROJECT_ROOT="/volume1/docker/tokenlysis"
REPO_URL="https://github.com/Tomp0uce/Tokenlysis.git"
BRANCH="main"
APP_NAME="tokenlysis"

REPO_DIR="$PROJECT_ROOT/repo"
CONFIG_DIR="$PROJECT_ROOT/config"
SECRETS_DIR="$CONFIG_DIR/secrets"
ENV_PUBLIC="$CONFIG_DIR/.env.public"   # édité côté NAS (ce fichier)
ENV_TARGET="$REPO_DIR/.env"            # .env lu par compose (dans le repo)

COMPOSE_BASE="$REPO_DIR/docker-compose.yml"
COMPOSE_SYN="$REPO_DIR/docker-compose.synology.yml"

DATA_DIR="$PROJECT_ROOT/data"          # volume hôte monté sur /data
LOG_FILE="$PROJECT_ROOT/update.log"

# Options de maintenance
RESET_SQLITE_ON_MIGRATION_ERROR="${RESET_SQLITE_ON_MIGRATION_ERROR:-false}"

mkdir -p "$REPO_DIR" "$CONFIG_DIR" "$DATA_DIR"
: > "$LOG_FILE"

# --- Détection docker compose ---
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  COMPOSE_RUN="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_RUN="docker-compose"
else
  echo "❌ Docker Compose introuvable" >> "$LOG_FILE"; exit 1
fi

command -v git >/dev/null 2>&1 || { echo "❌ Git indisponible" >> "$LOG_FILE"; exit 1; }

# --- Clone / update repo ---
if [ -d "$REPO_DIR/.git" ]; then
  git -C "$REPO_DIR" fetch --all --prune
  git -C "$REPO_DIR" checkout "$BRANCH"
  git -C "$REPO_DIR" reset --hard "origin/$BRANCH"
else
  git clone --branch "$BRANCH" "$REPO_URL" "$REPO_DIR"
fi

# --- Construire .env pour compose ---
TMP_ENV="$(mktemp)"
trap 'rm -f "$TMP_ENV"' EXIT

# 1) Base: .env.public
if [ -f "$ENV_PUBLIC" ]; then
  cat "$ENV_PUBLIC" > "$TMP_ENV"
else
  echo "⚠️  $ENV_PUBLIC absent, .env minimal" >> "$LOG_FILE"
fi

# 2) Defaults nécessaires (ancrés sur les variables attendues par le code)
grep -q '^TOKENLYSIS_DATABASE_URL=' "$TMP_ENV" || echo 'TOKENLYSIS_DATABASE_URL=sqlite+aiosqlite:////data/tokenlysis.db' >> "$TMP_ENV"
grep -q '^ALEMBIC_DATABASE_URL='    "$TMP_ENV" || echo 'ALEMBIC_DATABASE_URL=sqlite+pysqlite:////data/tokenlysis.db'   >> "$TMP_ENV"
grep -q '^DATABASE_URL='            "$TMP_ENV" || echo 'DATABASE_URL=sqlite+pysqlite:////data/tokenlysis.db'            >> "$TMP_ENV"

grep -q '^BUDGET_FILE='             "$TMP_ENV" || echo 'BUDGET_FILE=/data/budget.json'           >> "$TMP_ENV"
grep -q '^CMC_BUDGET_FILE='         "$TMP_ENV" || echo 'CMC_BUDGET_FILE=/data/cmc_budget.json'   >> "$TMP_ENV"
grep -q '^CG_THROTTLE_MS='          "$TMP_ENV" || echo 'CG_THROTTLE_MS=2100'                     >> "$TMP_ENV"
grep -q '^PYTHONPATH='              "$TMP_ENV" || echo 'PYTHONPATH=/app'                         >> "$TMP_ENV"

# 3) Ne jamais “réparer” TOKENLYSIS_DATABASE_URL en pysqlite (il doit rester aiosqlite)
#    Par contre, s’assurer que DATABASE_URL & ALEMBIC_DATABASE_URL sont bien en pysqlite
sed -i 's#^DATABASE_URL=sqlite:////data/#DATABASE_URL=sqlite+pysqlite:////data/#' "$TMP_ENV" || true
sed -i 's#^ALEMBIC_DATABASE_URL=sqlite:////data/#ALEMBIC_DATABASE_URL=sqlite+pysqlite:////data/#' "$TMP_ENV" || true

# 4) Versionning build
RUN="$(git -C "$REPO_DIR" rev-list --count HEAD 2>/dev/null || echo 0)"
SHA="$(git -C "$REPO_DIR" rev-parse --short HEAD 2>/dev/null || echo 0000000)"
BUILD_UTC="$(date -u +%Y%m%d%H%M%S)"

sed -i '/^APP_VERSION=/d' "$TMP_ENV" || true
sed -i '/^GIT_COMMIT=/d'  "$TMP_ENV" || true
sed -i '/^BUILD_TIME=/d'  "$TMP_ENV" || true
{
  echo "APP_VERSION=1.0.${RUN}"
  echo "GIT_COMMIT=${SHA}"
  echo "BUILD_TIME=${BUILD_UTC}"
} >> "$TMP_ENV"

# 5) Injection de secrets (un fichier = une variable)
if [ -d "$SECRETS_DIR" ]; then
  echo "" >> "$TMP_ENV"
  echo "# --- BEGIN injected secrets ---" >> "$TMP_ENV"
  for f in "$SECRETS_DIR"/*; do
    [ -f "$f" ] || continue
    var="$(basename "$f")"
    sed -i "/^${var}=.*/d" "$TMP_ENV" || true
    value="$(tr -d '\r' < "$f")"
    printf '%s=%s\n' "$var" "$value" >> "$TMP_ENV"
  done
  echo "# --- END injected secrets ---" >> "$TMP_ENV"
fi

# 6) Écrit le .env final dans le repo (lu par compose et par l’app via pydantic_settings)
cp "$TMP_ENV" "$ENV_TARGET"

# --- Lancement ---
mkdir -p "$DATA_DIR"
if [ -f "$COMPOSE_SYN" ]; then
  (cd "$REPO_DIR" && $COMPOSE_RUN -p "$APP_NAME" -f "$COMPOSE_BASE" -f "$COMPOSE_SYN" up -d --build --remove-orphans)
else
  (cd "$REPO_DIR" && $COMPOSE_RUN -p "$APP_NAME" -f "$COMPOSE_BASE" up -d --build --remove-orphans)
fi

# --- Option de reset SQLite si Alembic coince (dev uniquement) ---
if [ "$RESET_SQLITE_ON_MIGRATION_ERROR" = "true" ]; then
  sleep 3
  if ! (docker logs "$APP_NAME" 2>&1 | grep -q 'INFO  \[alembic.runtime.migration\] Running upgrade'); then
    echo "⚠️  Reset DB SQLite (dev)..." >> "$LOG_FILE"
    rm -f "$DATA_DIR/tokenlysis.db"
    (cd "$REPO_DIR" && $COMPOSE_RUN -p "$APP_NAME" up -d --build --remove-orphans)
  fi
fi

echo "✅ Déploiement terminé."
