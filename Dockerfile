FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps kept minimal; external OSINT binaries (theHarvester etc.) are added
# per-module in later phases.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --upgrade pip && pip install -e ".[ui]"

COPY . .

EXPOSE 8000
CMD ["uvicorn", "weft.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
