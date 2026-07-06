FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY backend/requirements.api.txt backend/requirements.api.txt
RUN pip install --no-cache-dir -r backend/requirements.api.txt

COPY backend/ backend/
COPY data/ data/

WORKDIR /app/backend

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
