#!/bin/sh
# Tokenlysis - Déploiement Synology (Option 1: SQLite sync)
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
ENV_PUBLIC="$CONFIG_DIR/.env.public"   # variables publiques côté NAS
ENV_TARGET="$REPO_DIR/.env"            # .env lu par docker compose (dans le repo)

COMPOSE_BASE="$REPO_DIR/docker-compose.yml"
COMPOSE_SYN="$REPO_DIR/docker-compose.synology.yml"

DATA_DIR="$PROJECT_ROOT/data"          # volume hôte monté sur /data dans le conteneur
LOG_FILE="$PROJECT_ROOT/update.log"

# --- Log header (reset) ---
{
  echo "==============================="
  echo "Tokenlysis - Déploiement $(date '+%Y-%m-%d %H:%M:%S')"
  echo "Root    : $PROJECT_ROOT"
  echo "Repo    : $REPO_DIR (branch: $BRANCH)"
  echo "Compose : $COMPOSE_BASE + $COMPOSE_SYN"
  echo "Data    : $DATA_DIR  (→ /data)"
  echo "==============================="
} > "$LOG_FILE"

# --- Prépare arbo ---
mkdir -p "$PROJECT_ROOT" "$CONFIG_DIR" "$SECRETS_DIR" "$DATA_DIR"
chmod 700 "$SECRETS_DIR" || true

# --- Détection docker compose ---
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  COMPOSE_RUN="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_RUN="docker-compose"
elif [ -x /usr/local/bin/docker-compose ]; then
  COMPOSE_RUN="/usr/local/bin/docker-compose"
else
  echo "❌ Aucune commande Docker Compose trouvée." >> "$LOG_FILE"; exit 1
fi

# --- Dépendance git ---
command -v git >/dev/null 2>&1 || { echo "❌ Git indisponible." >> "$LOG_FILE"; exit 1; }

# --- Clone / update repo ---
if [ -d "$REPO_DIR/.git" ]; then
  {
    echo "➡️  Mise à jour du dépôt…"
    git -C "$REPO_DIR" fetch --all --prune
    git -C "$REPO_DIR" checkout "$BRANCH"
    git -C "$REPO_DIR" reset --hard "origin/$BRANCH" || git -C "$REPO_DIR" reset --hard "$BRANCH"
  } >> "$LOG_FILE" 2>&1
else
  {
    echo "➡️  Clonage du dépôt…"
    rm -rf "$REPO_DIR"
    git clone --depth=1 --branch "$BRANCH" "$REPO_URL" "$REPO_DIR"
  } >> "$LOG_FILE" 2>&1
fi

# --- Génération .env (base publique + secrets), + version auto ---
{
  echo "➡️  Génération du .env…"
  TMP_ENV="$(mktemp)"

  # 1) Variables publiques si présentes (filtre KEY=VALUE) + suppression des CR Windows
  if [ -f "$ENV_PUBLIC" ]; then
    grep -E '^[A-Za-z_][A-Za-z0-9_]*=.*' "$ENV_PUBLIC" | tr -d '\r' > "$TMP_ENV"
  else
    : > "$TMP_ENV"
  fi

  # 2) Normalisations:
  #    - chemins host → chemins conteneur (/data)
  #    - forcer driver **sync** pour sqlite (Option 1)
  sed -i 's#sqlite:////volume1/docker/tokenlysis/data/#sqlite+pysqlite:////data/#g' "$TMP_ENV" || true
  sed -i 's#sqlite:////app/data/#sqlite+pysqlite:////data/#g' "$TMP_ENV" || true

  # 2-bis) Répare un DSN sqlite raccourci/incorrect
  sed -i 's#^DATABASE_URL=sqlite$#DATABASE_URL=sqlite+pysqlite:////data/tokenlysis.db#g' "$TMP_ENV" || true

  # 3) Valeurs par défaut si absentes (persistance + throttle + PYTHONPATH)
  grep -q '^DATABASE_URL='             "$TMP_ENV" || echo 'DATABASE_URL=sqlite+pysqlite:////data/tokenlysis.db' >> "$TMP_ENV"
  grep -q '^TOKENLYSIS_DATABASE_URL='  "$TMP_ENV" || echo 'TOKENLYSIS_DATABASE_URL=sqlite+pysqlite:////data/tokenlysis.db' >> "$TMP_ENV"
  grep -q '^ALEMBIC_DATABASE_URL='     "$TMP_ENV" || echo 'ALEMBIC_DATABASE_URL=sqlite+pysqlite:////data/tokenlysis.db' >> "$TMP_ENV"
  grep -q '^BUDGET_FILE='              "$TMP_ENV" || echo 'BUDGET_FILE=/data/budget.json'           >> "$TMP_ENV"
  grep -q '^CMC_BUDGET_FILE='          "$TMP_ENV" || echo 'CMC_BUDGET_FILE=/data/cmc_budget.json'   >> "$TMP_ENV"
  grep -q '^CG_THROTTLE_MS='           "$TMP_ENV" || echo 'CG_THROTTLE_MS=2100'                     >> "$TMP_ENV"
  grep -q '^PYTHONPATH='               "$TMP_ENV" || echo 'PYTHONPATH=/app'                         >> "$TMP_ENV"

  # 3-bis) Duplique DATABASE_URL → TOKENLYSIS_DATABASE_URL si ce dernier absent
  if ! grep -q '^TOKENLYSIS_DATABASE_URL=' "$TMP_ENV" && grep -q '^DATABASE_URL=' "$TMP_ENV"; then
    val="$(grep '^DATABASE_URL=' "$TMP_ENV" | tail -n1 | cut -d'=' -f2-)"
    echo "TOKENLYSIS_DATABASE_URL=$val" >> "$TMP_ENV"
  fi
  # 3-ter) Si ALEMBIC_DATABASE_URL absent mais DATABASE_URL présent, assure un DSN sync
  if ! grep -q '^ALEMBIC_DATABASE_URL=' "$TMP_ENV" && grep -q '^DATABASE_URL=' "$TMP_ENV"; then
    echo "ALEMBIC_DATABASE_URL=sqlite+pysqlite:////data/tokenlysis.db" >> "$TMP_ENV"
  fi

  # 4) Versioning auto depuis l’état exact du repo
  sed -i '/^APP_VERSION=/d'  "$TMP_ENV" || true
  sed -i '/^GIT_COMMIT=/d'   "$TMP_ENV" || true
  sed -i '/^BUILD_TIME=/d'   "$TMP_ENV" || true

  RUN="$(git -C "$REPO_DIR" rev-list --count HEAD 2>/dev/null || echo 0)"
  SHA="$(git -C "$REPO_DIR" rev-parse --short HEAD 2>/dev/null || echo 0000000)"
  BUILD_UTC="$(date -u +%Y%m%d%H%M%S)"

  APP_VERSION="1.0.${RUN}"
  {
    echo "APP_VERSION=${APP_VERSION}"
    echo "GIT_COMMIT=${SHA}"
    echo "BUILD_TIME=${BUILD_UTC}"
  } >> "$TMP_ENV"
  echo "ℹ️  APP_VERSION: ${APP_VERSION} (commit ${SHA}, ${BUILD_UTC}Z)" >> "$LOG_FILE"

  # 5) Injection de secrets (un fichier = une variable)
  if [ -d "$SECRETS_DIR" ]; then
    echo "" >> "$TMP_ENV"
    echo "# --- BEGIN injected secrets ---" >> "$TMP_ENV"
    for f in "$SECRETS_DIR"/*; do
      [ -f "$f" ] || continue
      var="$(basename "$f")"
      sed -i "/^${var}=.*/d" "$TMP_ENV" || true
      value="$(tr -d '\r' < "$f")"
      value_escaped="$(printf '%s' "$value" | sed -e 's/[\\&]/\\&/g')"
      printf '%s=%s\n' "$var" "$value_escaped" >> "$TMP_ENV"
      chmod 600 "$f"
    done
    echo "# --- END injected secrets ---" >> "$TMP_ENV"
  fi

  mv "$TMP_ENV" "$ENV_TARGET"
  chmod 600 "$ENV_TARGET"

  if grep -q '^COINGECKO_API_KEY=' "$ENV_TARGET"; then
    echo "ℹ️  COINGECKO_API_KEY : définie (valeur masquée)" >> "$LOG_FILE"
  else
    echo "⚠️  COINGECKO_API_KEY : non définie (mode public/demo)" >> "$LOG_FILE"
  fi
} >> "$LOG_FILE" 2>&1

# --- Patches de docker-compose (forcer sqlite **sync**) ---
{
  echo "➡️  Patch des docker-compose pour pysqlite…"
  for f in "$COMPOSE_BASE" "$COMPOSE_SYN"; do
    [ -f "$f" ] || continue
    # Corrige d’éventuels DSN async restants
    sed -i 's#sqlite+aiosqlite:////data/#sqlite+pysqlite:////data/#g' "$f" || true
  done
} >> "$LOG_FILE" 2>&1

# --- Build / pull / up ---
{
  echo "➡️  Build + (re)démarrage…"

  if [ -f "$COMPOSE_SYN" ]; then
    (cd "$REPO_DIR" && $COMPOSE_RUN -p "$APP_NAME" -f "$COMPOSE_BASE" -f "$COMPOSE_SYN" pull || true)
    (cd "$REPO_DIR" && $COMPOSE_RUN -p "$APP_NAME" -f "$COMPOSE_BASE" -f "$COMPOSE_SYN" up -d --build --remove-orphans)
  else
    echo "ℹ️  $COMPOSE_SYN introuvable, utilisation de $COMPOSE_BASE uniquement." >> "$LOG_FILE"
    (cd "$REPO_DIR" && $COMPOSE_RUN -p "$APP_NAME" -f "$COMPOSE_BASE" pull || true)
    (cd "$REPO_DIR" && $COMPOSE_RUN -p "$APP_NAME" -f "$COMPOSE_BASE" up -d --build --remove-orphans)
  fi

  echo "✅ Terminé."
} >> "$LOG_FILE" 2>&1
