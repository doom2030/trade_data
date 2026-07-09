from fastapi import Request
from fastapi.responses import RedirectResponse

from app.core.config import get_settings

settings = get_settings()

PUBLIC_PATHS = {"/login", "/health"}


def is_authenticated(request: Request) -> bool:
    if "session" not in request.scope:
        return False
    return request.session.get("authenticated") is True


def require_auth(request: Request) -> RedirectResponse | None:
    path = request.url.path
    if path.startswith("/static"):
        return None
    if path in PUBLIC_PATHS:
        return None
    if is_authenticated(request):
        return None
    api_prefixes = ("/api/", "/symbols", "/klines", "/jobs", "/industries")
    if any(path.startswith(prefix) for prefix in api_prefixes):
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Not authenticated")
    return RedirectResponse(url="/login", status_code=303)


def verify_credentials(username: str, password: str) -> bool:
    return username == settings.admin_username and password == settings.admin_password
