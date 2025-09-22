"""Guard against deprecated FastAPI event hooks."""

from backend.app.main import app


def test_app_avoids_deprecated_on_event_hooks() -> None:
    """Ensure deprecated ``on_event`` hooks are not used anymore."""

    assert app.router.on_startup == []
    assert app.router.on_shutdown == []
