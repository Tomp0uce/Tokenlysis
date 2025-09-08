# syntax=docker/dockerfile:1
FROM python:3.11.8-slim

ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}
LABEL org.opencontainers.image.version=${APP_VERSION}

WORKDIR /app

COPY backend/requirements.txt ./
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY frontend ./frontend
COPY start.sh ./start.sh
RUN printf "%s" "${APP_VERSION}" > /app/VERSION \
 && printf "window.APP_VERSION='%s';\n" "${APP_VERSION}" > /app/frontend/app-version.js

EXPOSE 8002
RUN chmod +x /app/start.sh
CMD ["/app/start.sh"]
