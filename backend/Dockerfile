# RKM Cinema API — FastAPI backend (modular production entrypoint)
FROM python:3.11-slim

WORKDIR /app

# Copy the full application tree needed to run the modular API
# (api/, services/, domain/, core/, config/, infrastructure/, application/)
# plus requirements. `infrastructure/` (persistence seam) and `application/`
# (use-case commands) are both required at import time by Phase 10/11 routes.
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Semantic search (SEARCH_IMPROVEMENT_PLAN Phase 6): BAKE the embedding model into the image.
#
# ⚠ Two reasons, both about the person waiting for a search: a container that fetched the model on
# its first conversational query would stall that query behind ~59 MB of download, and a box whose
# outbound network is down (or rate-limited by a proxy) would lose the feature entirely. The model
# is 59 MB of weights + a tokenizer, deliberately the smallest one that measured well enough
# (plan §3), and HF_HOME keeps it inside the image rather than in a runtime-writable cache.
#
# ⚠ The failure of this RUN is a BUILD failure, on purpose: a silent skip would ship an image whose
# semantic search quietly does nothing.
ENV HF_HOME=/opt/rkm-models
RUN python -c "from model2vec import StaticModel; StaticModel.from_pretrained('minishlab/potion-base-8M')" \
    && du -sh /opt/rkm-models

COPY api /app/api
COPY services /app/services
COPY domain /app/domain
COPY core /app/core
COPY config /app/config
COPY infrastructure /app/infrastructure
COPY application /app/application
COPY jobs /app/jobs
# scripts/ is imported by jobs/add_watchlist.py at request time
# (`from scripts.add_watchlist_cron import main`) for the on-demand refresh
# button. Without it the endpoint fails with "No module named 'scripts'".
COPY scripts /app/scripts

# .env is injected at runtime via env_file (docker-compose) or docker run -e.
# API keys for Radarr/Sonarr/TMDB/Plex/Emby are read from env only.
# watchlist.json is volume-mounted at /app/watchlist.json (read-only).

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=10).status==200 else 1)"

# Modular production entrypoint (single source of truth).
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
