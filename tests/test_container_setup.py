from pathlib import Path


def test_alembic_ini_copied_in_dockerfile() -> None:
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"
    content = dockerfile.read_text()
    assert "COPY alembic.ini ./alembic.ini" in content


def test_start_sh_uses_absolute_alembic_path() -> None:
    start_script = Path(__file__).resolve().parents[1] / "start.sh"
    content = start_script.read_text()
    assert "alembic -c /app/alembic.ini upgrade head" in content


def test_start_sh_does_not_use_relative_alembic_path() -> None:
    start_script = Path(__file__).resolve().parents[1] / "start.sh"
    content = start_script.read_text()
    assert "alembic -c alembic.ini upgrade head" not in content


def test_dockerfile_does_not_copy_alembic_to_wrong_path() -> None:
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"
    content = dockerfile.read_text()
    assert "COPY alembic.ini /app/alembic.ini" not in content


def test_main_does_not_call_run_migrations() -> None:
    main_py = Path(__file__).resolve().parents[1] / "backend/app/main.py"
    content = main_py.read_text()
    assert "run_migrations(" not in content
