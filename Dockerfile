# syntax=docker/dockerfile:1
FROM python:3.11-slim
ARG APP_VERSION=dev
WORKDIR /app

# Generate a VERSION file containing the current commit hash. When a specific
# APP_VERSION build argument is provided it is used instead.
COPY .git /tmp/git
RUN if [ "$APP_VERSION" = "dev" ]; then \
        python - <<'PY' > VERSION
import pathlib

root = pathlib.Path('/tmp/git')
head = (root / 'HEAD').read_text().strip()
if head.startswith('ref:'):
    ref = head.split(' ', 1)[1]
    print((root / ref).read_text().strip()[:7])
else:
    print(head[:7])
PY
      ; else echo "$APP_VERSION" > VERSION; fi && rm -rf /tmp/git
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY frontend ./frontend
EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
