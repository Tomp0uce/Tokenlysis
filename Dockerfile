# syntax=docker/dockerfile:1
FROM python:3.11-slim
ARG APP_VERSION=dev
WORKDIR /app

# Derive a version string from the last commit timestamp when no explicit APP_VERSION is provided.
COPY .git /tmp/git
RUN if [ "$APP_VERSION" = "dev" ]; then \
        python - <<'PY' > VERSION
import datetime, pathlib, zlib

root = pathlib.Path('/tmp/git')
head = (root / 'HEAD').read_text().strip()
if head.startswith('ref:'):
    ref = head.split(' ', 1)[1]
    commit = (root / ref).read_text().strip()
else:
    commit = head.strip()
obj = root / 'objects' / commit[:2] / commit[2:]
data = zlib.decompress(obj.read_bytes())
for line in data.splitlines():
    if line.startswith(b'committer '):
        parts = line.split()
        ts = int(parts[-2])
        tz = parts[-1].decode()
        sign = 1 if tz[0] == '+' else -1
        hours = int(tz[1:3])
        minutes = int(tz[3:5])
        offset = datetime.timedelta(hours=hours, minutes=minutes) * sign
        dt = datetime.datetime.fromtimestamp(ts, datetime.timezone(offset))
        print(dt.isoformat())
        break
PY
    else \
        echo "$APP_VERSION" > VERSION; \
    fi && rm -rf /tmp/git
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY frontend ./frontend
EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
