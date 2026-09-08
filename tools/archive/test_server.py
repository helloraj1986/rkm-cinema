#!/usr/bin/env python3
"""Dev-only local full-stack server: /api -> FastAPI backend, / -> static files.
Mirrors the production nginx layout on a single origin (nginx proxies /api to api:8000
and serves static files itself, so api.py keeps its /api-prefixed routes; this harness
re-registers those routes minus the prefix).

Run: uvicorn test_server:app --host 127.0.0.1 --port 8124
"""
from fastapi import FastAPI, routing
from fastapi.staticfiles import StaticFiles
import api

app = FastAPI(title="RKM Cinema (dev composite)")

for route in api.app.routes:
    if isinstance(route, routing.APIRoute) and route.path.startswith("/api"):
        # nginx proxies /api/* verbatim to api:8000, so routes keep their full path here too
        app.add_api_route(
            route.path,
            route.endpoint,
            methods=route.methods,
            name=route.name,
            response_model=route.response_model,
        )

app.mount("/", StaticFiles(directory="/workspace/media/watchlist", html=True), name="static")