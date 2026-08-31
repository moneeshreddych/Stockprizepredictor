FROM python:3.12-slim

WORKDIR /app

COPY requirements-cloudrun.txt .

RUN pip install --no-cache-dir -r requirements-cloudrun.txt

COPY . .

# Run Flask API on all interfaces (0.0.0.0) so it's accessible from outside
CMD ["python", "-m", "flask", "--app", "api.news_api", "run", "--host", "0.0.0.0", "--port", "${PORT:-5000}"]