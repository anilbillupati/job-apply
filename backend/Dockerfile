FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt \
    && python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

COPY . .

RUN useradd --create-home --uid 1000 app && mkdir -p /data && chown -R app /data /app
USER app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
