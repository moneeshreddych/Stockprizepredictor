FROM python:3.12-slim

WORKDIR /app

# Install dependencies for collector
COPY requirements.txt .
RUN pip install --no-cache-dir fastapi uvicorn httpx

COPY src/collector ./src/collector
COPY src/database ./src/database
COPY .env .

EXPOSE 8001

CMD ["uvicorn", "src.collector.main:app", "--host", "0.0.0.0", "--port", "8001"]
