# RKM Cinema API — FastAPI backend (modular production entrypoint)
FROM python:3.11-slim

WORKDIR /app

# Copy the full application tree needed to run the modular API
# (api/, services/, domain/, core/, config/, infrastructure/, application/)
# plus requirements. `infrastructure/` (persistence seam) and `application/`
# (use-case commands) are both required at import time by Phase 10/11 routes.
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY api /app/api
COPY services /app/services
COPY domain /app/domain
COPY core /app/core
COPY config /app/config
COPY infrastructure /app/infrastructure
COPY application /app/application

# .env is injected at runtime via env_file (docker-compose) or docker run -e.
# API keys for Radarr/Sonarr/TMDB/Plex/Emby are read from env only.
# watchlist.json is volume-mounted at /app/watchlist.json (read-only).

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=10).status==200 else 1)"

# Modular production entrypoint (single source of truth).
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
