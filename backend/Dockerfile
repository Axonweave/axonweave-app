FROM python:3.12-slim

WORKDIR /app

# System deps for psycopg (PostgreSQL client)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# This image is the development image (uvicorn --reload): it includes the test and lint tools
# from requirements-dev.txt so `docker compose exec backend pytest` works. A production image
# should install requirements.txt only.
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
