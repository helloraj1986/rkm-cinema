# Archived legacy monolith

`api_legacy_monolith.py` is the pre-refactor single-file FastAPI backend
(`uvicorn api:app`). It has been **superseded** by the modular architecture and
is archived for reference only.

- Production now runs `uvicorn api.main:app` (see `Dockerfile`).
- All routes moved to `api/routes/*`; business logic to `services/` + `domain/`.
- No production code imports this file.

Delete this file once you are confident the modular backend is fully verified
in production.
