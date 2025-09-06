FROM python:3.11-slim
WORKDIR /app
ENV APP_VERSION="123456789"
ENV COINGECKO_API_KEY="XXXXX"
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY frontend ./frontend
EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
