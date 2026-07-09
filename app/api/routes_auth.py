
from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from app.core.auth import verify_credentials
from app.core.config import get_settings
from app.core.templates import templates

router = APIRouter(tags=["auth"])
settings = get_settings()


@router.get("/login")
def login_page(request: Request):
    if request.session.get("authenticated"):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    if verify_credentials(username, password):
        request.session["authenticated"] = True
        request.session["username"] = username
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        {"error": "用户名或密码错误"},
        status_code=401,
    )


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
