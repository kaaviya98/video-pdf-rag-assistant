# Setup

Required services: PostgreSQL, Weaviate, Redis, and RabbitMQ for Celery workers. Copy `.env.example` to `.env`, set credentials, install dependencies with `uv sync`, run `uv run python manage.py migrate --run-syncdb`, and launch `uv run uvicorn app.main:app --reload`. OpenAPI is available at `/docs`.
