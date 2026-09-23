FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
# See workers/ocr_worker/Dockerfile: the cache is reused across builds and
# does not end up in the image.
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt

COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
