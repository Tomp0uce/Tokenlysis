import re
from typing import Any, Callable, Dict, List, Tuple


class HTTPException(Exception):
    def __init__(self, status_code: int, detail: Any = None):
        self.status_code = status_code
        self.detail = detail


class FastAPI:
    def __init__(self, title: str | None = None):
        self.title = title
        self.routes: List[Tuple[str, str, Callable]] = []

    def add_middleware(self, *args, **kwargs):
        # middleware ignored for mock
        pass

    def get(self, path: str):
        def decorator(func: Callable):
            self.routes.append(("GET", path, func))
            return func
        return decorator
