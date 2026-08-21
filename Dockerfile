# RKM Cinema API — FastAPI backend
FROM python:3.11-slim

WORKDIR /app

# Copy only what the API needs
COPY api.py /app/api.py

RUN pip install --no-cache-dir fastapi "uvicorn[standard]" requests

# .env is injected at runtime via env_file (docker-compose) or docker run -e
# API keys for Radarr/Sonarr/TMDB/TVDB/Plex/Jellyfin are read from env only.

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health').status==200 else 1)"

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
