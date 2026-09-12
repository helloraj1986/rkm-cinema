"""FastAPI application factory."""
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import get_config
from core.logging import setup_logging

from api.routes import health, config, status, download, search, library, quality, suggest
from api.routes import auth as auth_routes
from api.routes import admin_users as admin_users_routes
from api.routes import search_global as search_global_routes
from api.routes import jellyfin_poster as jellyfin_poster_routes
from api.routes import jellyfin_stream as jellyfin_stream_routes
from api.routes import jellyfin_hls as jellyfin_hls_routes
from api.routes import jellyfin_tracks as jellyfin_tracks_routes
from api.routes import jellyfin_subtitles as jellyfin_subtitles_routes
from api.routes import jellyfin_detail as jellyfin_detail_routes
from api.routes import jellyfin_similar as jellyfin_similar_routes
from api.routes import media as media_routes
from api.routes import watchlist as watchlist_routes
from api.routes import reconcile as reconcile_routes
from api.routes import jobs as jobs_routes
from api.session import require_session


#: Phase C: ONE dependency, applied per ROUTER, publishes the signed-in identity for every app
#: route (``api/session.py`` explains the seam). Before this existed Phase C could not have worked
#: at all — ``require_session`` was referenced by no route, so no media call ever saw a profile and
#: every one of them ran on the administrator's credential.
#:
#: ONE line per router, not a ``Depends`` on ~40 endpoints: a site that forgot it would silently
#: keep serving the administrator's library and watch state to a household member, which is the
#: exact failure this workstream exists to prevent.
#:
#: Deliberately NOT applied to ``/api/health`` (the Dockerfile HEALTHCHECK calls it — a 401 there
#: marks the api unhealthy and cascades) or ``/api/auth/*`` (sign-in must be reachable signed out;
#: those routes read the session directly and a session-less call is not an error for them).
#: With ``RKM_AUTH_REQUIRED=false`` this changes NOTHING observable — it only publishes the
#: identity, and a missing session stays a valid anonymous request.
SESSION_SCOPED = [Depends(require_session)]


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
    # Auth / multi-user (AUTH_MULTIUSER_PLAN Phase 0): sign in/out + who am I. NOT
    # enforced yet — RKM_AUTH_REQUIRED is false until Phase 2 arms it (the login UI
    # ships first, so an enforcement deploy can never lock the user out).
    app.include_router(auth_routes.router, prefix="/api")
    # Household accounts (AUTH_MULTIUSER_PLAN Phase 1b): admin-only, session-STRICT even
    # while the rest of the app is unenforced — these routes create and delete accounts.
    app.include_router(admin_users_routes.router, prefix="/api")
    # Phase C: every APP route below is session-scoped, so a media call is made as the selected
    # profile rather than as the administrator. See SESSION_SCOPED above.
    app.include_router(config.router, prefix="/api", dependencies=SESSION_SCOPED)
    app.include_router(status.router, prefix="/api", dependencies=SESSION_SCOPED)
    app.include_router(download.router, prefix="/api", dependencies=SESSION_SCOPED)
    app.include_router(search.router, prefix="/api", dependencies=SESSION_SCOPED)
    app.include_router(search_global_routes.router, prefix="/api", dependencies=SESSION_SCOPED)
    app.include_router(library.router, prefix="/api", dependencies=SESSION_SCOPED)
    app.include_router(quality.router, prefix="/api", dependencies=SESSION_SCOPED)
    app.include_router(jellyfin_poster_routes.router, prefix="/api", dependencies=SESSION_SCOPED)
    app.include_router(jellyfin_stream_routes.router, prefix="/api", dependencies=SESSION_SCOPED)
    app.include_router(jellyfin_hls_routes.router, prefix="/api", dependencies=SESSION_SCOPED)
    app.include_router(jellyfin_tracks_routes.router, prefix="/api", dependencies=SESSION_SCOPED)
    app.include_router(jellyfin_subtitles_routes.router, prefix="/api", dependencies=SESSION_SCOPED)
    app.include_router(jellyfin_detail_routes.router, prefix="/api", dependencies=SESSION_SCOPED)
    app.include_router(jellyfin_similar_routes.router, prefix="/api", dependencies=SESSION_SCOPED)
    app.include_router(suggest.router, prefix="/api", dependencies=SESSION_SCOPED)
    # Phase 10 — resource API (spec §17).
    app.include_router(media_routes.router, prefix="/api", dependencies=SESSION_SCOPED)
    app.include_router(watchlist_routes.router, prefix="/api", dependencies=SESSION_SCOPED)
    app.include_router(reconcile_routes.router, prefix="/api", dependencies=SESSION_SCOPED)
    app.include_router(jobs_routes.router, prefix="/api", dependencies=SESSION_SCOPED)

    @app.on_event("startup")
    async def startup():
        import logging
        # Validate required config
        missing = cfg.validate_required()
        if missing:
            logging.warning("Missing required config: %s", missing)
        # Subtitles (SUBTITLES_OPENSUBTITLES_PLAN §3.1): OpenSubtitles is OPTIONAL,
        # so it is never added to validate_required() — the app must boot, browse and
        # play without it, and only the subtitle SEARCH section degrades. ONE clear
        # line, naming the anonymous/key-less case so "why is search empty?" is
        # answerable from the log. Never logs the key or the password.
        if cfg.has_opensubtitles():
            logging.info("OpenSubtitles enabled (%s) — subtitle search languages: %s",
                         "login configured" if cfg.has_opensubtitles_login()
                         else "anonymous, no login",
                         ", ".join(cfg.opensubtitles_languages()))
        else:
            reason = ("disabled by OPENSUBTITLES_ENABLED" if cfg.opensubtitles_disabled()
                      else "no OPENSUBTITLES_API_KEY")
            logging.info("OpenSubtitles not configured (%s) — subtitle search disabled", reason)
        # Phase 14: start the in-process job scheduler if enabled (spec §26/§40).
        try:
            from jobs.scheduler import start_if_enabled
            if start_if_enabled(config=cfg):
                logging.info("RKM job scheduler started")
        except Exception:
            logging.exception("Failed to start job scheduler")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)