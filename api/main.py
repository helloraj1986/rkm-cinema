"""FastAPI application factory."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import get_config
from core.logging import setup_logging

from api.routes import health, config, status, download, search, library, quality


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

    @app.on_event("startup")
    async def startup():
        # Validate required config
        missing = cfg.validate_required()
        if missing:
            import logging
            logging.warning("Missing required config: %s", missing)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)