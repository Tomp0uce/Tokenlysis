from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from starlette.websockets import WebSocket

from .admin.setup import mount_admin
from .api import deps
from .api.routes import files, scores, tasks, users
from .api.routes.scores import _mock_scores 
from .core.config import get_settings
from .core.observability import configure_observability
from .core.security import AuthenticatedUser


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    configure_observability(app)

    app.include_router(users.router, prefix="/api")
    app.include_router(tasks.router, prefix="/api")
    app.include_router(files.router, prefix="/api")
    app.include_router(scores.router, prefix="/api")
    app.state.admin = mount_admin(app)

    @app.get("/api/stream/scores")
    async def stream_scores(
        _: AuthenticatedUser = Depends(deps.require_role("stream", "read")),
    ) -> EventSourceResponse:
        async def event_publisher() -> AsyncGenerator[dict[str, str], None]:
            for coin in ("btc", "eth"):
                payload = json.dumps({"coin": coin, "score": 0.75})
                yield {"event": "score", "data": payload}
                await asyncio.sleep(0)

        return EventSourceResponse(event_publisher())
    
    @app.get("/readyz", include_in_schema=False)
    def readyz():
        return {"status": "ok"}

    @app.get("/", include_in_schema=False)
    def root():
        return {"service": settings.app_name, "docs": "/docs"}

    @app.get("/api", include_in_schema=False)
    def api_index():
        return {"ok": True}
        
    @app.get("/api/ranking")
    async def get_ranking(_: deps.AuthenticatedUser = Depends(deps.require_role("stream", "read"))):
        return _mock_scores()

    @app.get("/livez", include_in_schema=False)
    def livez():
        return Response(status_code=204)

    @app.websocket("/ws/scores")
    async def websocket_scores(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            while True:
                message = await websocket.receive_json()
                coin = message.get("coin", "btc")
                await websocket.send_json({"coin": coin, "score": 0.82})
        except Exception:  # pragma: no cover
            await websocket.close()

    return app


app = create_app()
