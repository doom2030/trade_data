from datetime import date, timedelta
from urllib.parse import quote, unquote

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.templates import templates
from app.models import CollectJob, CollectJobItem
from app.schemas.kline import BackfillRequest
from app.services.dashboard_service import DashboardService
from app.services.industry_query_service import IndustryQueryService
from app.services.job_command_service import JobCommandService
from app.services.job_query_service import JobQueryService
from app.services.symbol_query_service import SymbolQueryService

router = APIRouter(tags=["pages"])
settings = get_settings()

JOB_TYPES = [
    "sync_stock_meta", "sync_industry", "sync_trade_calendar", "backfill_kline",
    "daily_update", "catchup_daily_update", "update_weekly", "update_monthly",
    "retry_failed_jobs", "manual_retry_failed_job", "manual_retry_failed_item",
    "manual_backfill_range", "quality_check",
]


def _ctx(request: Request, active_page: str, **extra):
    return {
        "request": request,
        "active_page": active_page,
        "username": request.session.get("username", "admin"),
        **extra,
    }


def _redirect_with_message(path: str, message: str) -> RedirectResponse:
    return RedirectResponse(f"{path}?message={quote(message)}", status_code=303)


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    stats = DashboardService(db).get_stats()
    return templates.TemplateResponse(request, "dashboard.html", _ctx(request, "dashboard", stats=stats))


@router.get("/charts")
def charts_page(
    request: Request,
    db: Session = Depends(get_db),
    symbol: str | None = None,
    frequency: str = "day",
    adjust: str = "forward",
    include_excluded: bool = False,
):
    symbols = SymbolQueryService(db).query_symbols(include_excluded=include_excluded)
    today = date.today()
    default_start = (today - timedelta(days=90)).isoformat()
    default_end = today.isoformat()
    default_symbol = symbol or (symbols[0].symbol if symbols else "")

    return templates.TemplateResponse(
        request,
        "charts.html",
        _ctx(
            request,
            "charts",
            symbols=symbols,
            default_symbol=default_symbol,
            default_frequency=frequency,
            default_adjust=adjust,
            default_start=default_start,
            default_end=default_end,
            include_excluded=include_excluded,
            max_natural_days=settings.manual_backfill_max_natural_days,
        ),
    )


@router.get("/symbols")
def symbols_page(
    request: Request,
    db: Session = Depends(get_db),
    board: str | None = None,
    status: str | None = None,
    keyword: str | None = None,
    include_excluded: bool = Query(False),
):
    symbols = SymbolQueryService(db).query_symbols(board, status, keyword, include_excluded)
    return templates.TemplateResponse(
        request,
        "symbols.html",
        _ctx(
            request,
            "symbols",
            symbols=symbols,
            board=board,
            status=status,
            keyword=keyword,
            include_excluded=include_excluded,
        ),
    )


@router.get("/industries")
def industries_page(request: Request, db: Session = Depends(get_db)):
    industries = IndustryQueryService(db).list_industries()
    return templates.TemplateResponse(request, "industries.html", _ctx(request, "industries", industries=industries))


@router.get("/industries/{industry_name:path}")
def industry_detail_page(industry_name: str, request: Request, db: Session = Depends(get_db)):
    name = unquote(industry_name)
    symbols = IndustryQueryService(db).list_symbols_by_industry(name)
    return templates.TemplateResponse(
        request,
        "industry_detail.html",
        _ctx(request, "industries", industry_name=name, symbols=symbols),
    )


@router.get("/jobs")
def jobs_page(
    request: Request,
    db: Session = Depends(get_db),
    status: str | None = None,
    job_type: str | None = None,
    message: str | None = None,
):
    jobs = JobQueryService(db).list_jobs(status, job_type, limit=100)
    return templates.TemplateResponse(
        request,
        "jobs.html",
        _ctx(
            request,
            "jobs",
            jobs=jobs,
            filter_status=status,
            filter_job_type=job_type,
            job_types=JOB_TYPES,
            message=message,
        ),
    )


@router.get("/jobs/{job_id}")
def job_detail_page(
    job_id: int,
    request: Request,
    db: Session = Depends(get_db),
    item_status: str | None = None,
    message: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=JobQueryService.MAX_JOB_ITEMS_LIMIT),
):
    job = db.get(CollectJob, job_id)
    if not job:
        return RedirectResponse("/jobs", status_code=303)
    query_service = JobQueryService(db)
    item_total = query_service.count_job_items(job_id, item_status)
    offset = max(0, offset)
    if item_total > 0:
        last_page_offset = max(0, ((item_total - 1) // limit) * limit)
        offset = min(offset, last_page_offset)
    items = query_service.list_job_items(job_id, item_status, offset, limit)
    return templates.TemplateResponse(
        request,
        "job_detail.html",
        _ctx(
            request,
            "jobs",
            job=job,
            items=items,
            item_status=item_status,
            message=message,
            item_offset=offset,
            item_limit=limit,
            item_total=item_total,
        ),
    )


@router.post("/jobs/{job_id}/retry")
def retry_job_form(job_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        result = JobCommandService(db).retry_job(job_id)
    except HTTPException as e:
        detail = e.detail if isinstance(e.detail, str) else "操作失败"
        if e.status_code == 404:
            return _redirect_with_message("/jobs", detail)
        return _redirect_with_message(f"/jobs/{job_id}", detail)
    return _redirect_with_message(f"/jobs/{result.job_id}", f"重试任务 #{result.job_id} 已创建")


@router.post("/job-items/{item_id}/retry")
def retry_item_form(item_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        result = JobCommandService(db).retry_item(item_id)
    except HTTPException as e:
        item = db.get(CollectJobItem, item_id)
        detail = e.detail if isinstance(e.detail, str) else "操作失败"
        if item:
            return _redirect_with_message(f"/jobs/{item.job_id}", detail)
        return _redirect_with_message("/jobs", detail)
    return _redirect_with_message(f"/jobs/{result.job_id}", f"重试任务 #{result.job_id} 已创建")


@router.post("/charts/backfill")
def charts_backfill_form(
    request: Request,
    db: Session = Depends(get_db),
    symbol: str = Form(...),
    frequency: str = Form(...),
    start: date = Form(...),
    end: date = Form(...),
):
    result = JobCommandService(db).create_backfill(
        BackfillRequest(symbol=symbol, frequency=frequency, start=start, end=end)
    )
    return _redirect_with_message(f"/jobs/{result.job_id}", f"补采任务 #{result.job_id} 已创建")
