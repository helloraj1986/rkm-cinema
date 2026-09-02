"""FastAPI application factory."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import get_config
from core.logging import setup_logging

from api.routes import health, config, status, download, search, library, quality, plex_thumb, suggest
from api.routes import media as media_routes
from api.routes import watchlist as watchlist_routes
from api.routes import reconcile as reconcile_routes
from api.routes import jobs as jobs_routes


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    # Setup logging
    setup_logging(level="INFO", json_format=False)

    cfg = get_config()

    app = FastAPI(
        title="RKM Cinema API",
        version="2.0",
        docs_url=None,
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routes
    app.include_router(health.router, prefix="/api")
    app.include_router(config.router, prefix="/api")
    app.include_router(status.router, prefix="/api")
    app.include_router(download.router, prefix="/api")
    app.include_router(search.router, prefix="/api")
    app.include_router(library.router, prefix="/api")
    app.include_router(quality.router, prefix="/api")
    app.include_router(plex_thumb.router, prefix="/api")
    app.include_router(suggest.router, prefix="/api")
    # Phase 10 — resource API (spec §17).
    app.include_router(media_routes.router, prefix="/api")
    app.include_router(watchlist_routes.router, prefix="/api")
    app.include_router(reconcile_routes.router, prefix="/api")
    app.include_router(jobs_routes.router, prefix="/api")

    @app.on_event("startup")
    async def startup():
        # Validate required config
        missing = cfg.validate_required()
        if missing:
            import logging
            logging.warning("Missing required config: %s", missing)
        # Phase 14: start the in-process job scheduler if enabled (spec §26/§40).
        try:
            from jobs.scheduler import start_if_enabled
            if start_if_enabled(config=cfg):
                import logging
                logging.info("RKM job scheduler started")
        except Exception:
            import logging
            logging.exception("Failed to start job scheduler")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)