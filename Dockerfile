FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY migrations/ migrations/
COPY *.py .

ENV GARMIN_TOKEN_CACHE_PATH=/data/garmin_tokens

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
