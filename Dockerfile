FROM python:3.12-slim

WORKDIR /app

COPY requirements-cloudrun.txt .

RUN pip install --no-cache-dir -r requirements-cloudrun.txt

COPY . .

# Run Flask API on all interfaces. Use a shell so ${PORT:-5000} is expanded.
CMD ["/bin/sh", "-c", "python -m flask --app api.news_api run --host 0.0.0.0 --port ${PORT:-5000}"]
