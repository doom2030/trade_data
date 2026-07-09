from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api import (
    routes_auth,
    routes_health,
    routes_industries,
    routes_jobs,
    routes_klines,
    routes_pages,
    routes_symbols,
)
from app.core.auth import PUBLIC_PATHS, is_authenticated
from app.core.config import get_settings
from app.core.logging import setup_logging

setup_logging()
settings = get_settings()

app = FastAPI(title="Trade Data", version="1.0.0")


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/static") or path in PUBLIC_PATHS:
        return await call_next(request)
    if not is_authenticated(request):
        if path.startswith("/api/"):
            return JSONResponse({"detail": "Not authenticated"}, status_code=401)
        return RedirectResponse("/login", status_code=303)
    return await call_next(request)


app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    max_age=settings.session_max_age_hours * 3600,
    same_site="lax",
    https_only=False,
)

app.include_router(routes_auth.router)
app.include_router(routes_health.router)
app.include_router(routes_symbols.router)
app.include_router(routes_industries.router)
app.include_router(routes_klines.router)
app.include_router(routes_jobs.router)
app.include_router(routes_pages.router)

static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
