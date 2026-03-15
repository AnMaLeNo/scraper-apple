FROM python:3.12-slim

WORKDIR /app

# Installer uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Dépendances Python (cache layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Code applicatif
COPY src/ src/
RUN uv sync --frozen --no-dev

# Fichier de routage (peut être monté en volume)
COPY filter_rules.json ./

# Dossier pour la BDD SQLite (à monter en volume)
RUN mkdir -p /data

ENTRYPOINT ["uv", "run", "python", "-u", "-m", "mac_scraper"]
