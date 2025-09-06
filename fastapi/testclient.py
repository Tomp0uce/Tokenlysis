import re
from urllib.parse import parse_qs
from typing import Any

from .app import HTTPException


class Response:
    def __init__(self, status_code: int, data: Any):
        self.status_code = status_code
        self._data = data

    def json(self):
        return self._data


class TestClient:
    def __init__(self, app):
        self.app = app

    def get(self, url: str):
        path, _, query = url.partition('?')
        params = {k: v[0] for k, v in parse_qs(query).items()}
        for method, route, func in self.app.routes:
            if method != 'GET':
                continue
            pattern = '^' + re.sub(r'{[^/]+}', r'([^/]+)', route) + '$'
            m = re.match(pattern, path)
            if m:
                keys = re.findall(r'{([^/]+)}', route)
                kwargs = {}
                for key, val in zip(keys, m.groups()):
                    kwargs[key] = int(val) if val.isdigit() else val
                try:
                    result = func(**{**kwargs, **params})
                    return Response(200, result)
                except HTTPException as exc:
                    return Response(exc.status_code, {'detail': exc.detail})
        return Response(404, {'detail': 'Not Found'})
