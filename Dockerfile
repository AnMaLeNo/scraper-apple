FROM python:3.12-slim

WORKDIR /app

# Dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code applicatif
COPY config.py scraper.py filters.py filter_rules.json ./

# Dossier pour la BDD SQLite (à monter en volume)
RUN mkdir -p /data

ENTRYPOINT ["python", "-u", "scraper.py"]
