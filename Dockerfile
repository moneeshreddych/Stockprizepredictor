FROM python:3.12-slim

WORKDIR /app

COPY requirements-cloudrun.txt .

RUN pip install --no-cache-dir -r requirements-cloudrun.txt

COPY news ./news

CMD ["python", "news/news_collector.py"]