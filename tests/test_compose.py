import pathlib


def read(path: str) -> str:
    return pathlib.Path(path).read_text()


def test_docker_compose_contains_env_and_volume():
    text = read("docker-compose.yml")
    assert "DATABASE_URL=sqlite:////data/tokenlysis.db" in text
    assert "BUDGET_FILE=/data/budget.json" in text
    assert "COINGECKO_PLAN=demo" in text
    assert "CG_THROTTLE_MS=2100" in text
    assert "./data:/data" in text


def test_synology_compose_contains_env_and_volume():
    text = read("docker-compose.synology.yml")
    assert "/volume1/docker/tokenlysis/data:/data" in text
    assert "DATABASE_URL=sqlite:////data/tokenlysis.db" in text
    assert "BUDGET_FILE=/data/budget.json" in text
    assert "COINGECKO_PLAN=demo" in text
    assert "CG_THROTTLE_MS=2100" in text


def test_start_script_runs_migrations():
    text = read("start.sh")
    assert "alembic -c alembic.ini upgrade head" in text
    assert "uvicorn backend.app.main:app" in text
