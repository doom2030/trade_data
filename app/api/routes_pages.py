from datetime import date, timedelta
from urllib.parse import quote, unquote

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.templates import JOB_TYPE_LABELS, templates
from app.models import CollectJob, CollectJobItem
from app.schemas.kline import BackfillRequest
from app.services.dashboard_service import DashboardService
from app.services.industry_query_service import IndustryQueryService
from app.services.job_command_service import JobCommandService
from app.services.job_query_service import JobQueryService
from app.services.symbol_query_service import SymbolQueryService

router = APIRouter(tags=["pages"])
settings = get_settings()

JOB_TYPES = list(JOB_TYPE_LABELS.keys())


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
    # Day-line default window: last 30 calendar days.
    default_start = (today - timedelta(days=30)).isoformat()
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
    industry: str | None = None,
    include_excluded: bool = Query(False),
):
    svc = SymbolQueryService(db)
    symbols = svc.query_symbols(board, status, keyword, include_excluded, industry)
    board_counts = svc.count_by_board(status, keyword, include_excluded, industry=None)
    industries = svc.list_industries(board, status, include_excluded)
    return templates.TemplateResponse(
        request,
        "symbols.html",
        _ctx(
            request,
            "symbols",
            symbols=symbols,
            board=board or "",
            status=status,
            keyword=keyword,
            industry=industry or "",
            include_excluded=include_excluded,
            board_tabs=svc.board_tabs(),
            board_counts=board_counts,
            industries=industries,
        ),
    )


@router.get("/industries")
def industries_page(request: Request, db: Session = Depends(get_db)):
    groups = IndustryQueryService(db).list_industries_grouped()
    return templates.TemplateResponse(
        request,
        "industries.html",
        _ctx(request, "industries", industry_groups=groups),
    )


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
    date_from: date | None = None,
    date_to: date | None = None,
    message: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(15, ge=1, le=JobQueryService.MAX_JOBS_LIMIT),
):
    query_service = JobQueryService(db)
    job_total = query_service.count_jobs(status, job_type, date_from, date_to)
    if job_total > 0:
        last_page_offset = max(0, ((job_total - 1) // limit) * limit)
        offset = min(offset, last_page_offset)
    jobs = query_service.list_jobs(
        status, job_type, limit=limit, offset=offset, date_from=date_from, date_to=date_to
    )
    return templates.TemplateResponse(
        request,
        "jobs.html",
        _ctx(
            request,
            "jobs",
            jobs=jobs,
            filter_status=status,
            filter_job_type=job_type,
            filter_date_from=date_from.isoformat() if date_from else "",
            filter_date_to=date_to.isoformat() if date_to else "",
            job_types=JOB_TYPES,
            message=message,
            job_offset=offset,
            job_limit=limit,
            job_total=job_total,
        ),
    )


@router.get("/jobs/run")
def job_runner_page(
    request: Request,
    message: str | None = None,
):
    today = date.today().isoformat()
    return templates.TemplateResponse(
        request,
        "job_run.html",
        _ctx(
            request,
            "jobs",
            today=today,
            message=message,
            max_natural_days=settings.manual_backfill_max_natural_days,
        ),
    )


@router.post("/jobs/run")
def trigger_job_form(
    request: Request,
    db: Session = Depends(get_db),
    action: str = Form(...),
    snapshot_date: date | None = Form(None),
    start: date | None = Form(None),
    end: date | None = Form(None),
    trade_date: date | None = Form(None),
    end_date: date | None = Form(None),
    up_to: date | None = Form(None),
    symbol: str | None = Form(None),
    frequency: str | None = Form(None),
    source: str = Form("auto"),
    sleep_seconds: float = Form(0.35),
    max_attempts: int = Form(3),
    limit: int = Form(500),
    job_id: int | None = Form(None),
):
    params = {
        "snapshot_date": snapshot_date or date.today(),
        "start": start,
        "end": end,
        "trade_date": trade_date or date.today(),
        "end_date": end_date or date.today(),
        "up_to": up_to or date.today(),
        "symbol": (symbol or "").strip(),
        "frequency": frequency,
        "source": source,
        "sleep_seconds": sleep_seconds,
        "max_attempts": max_attempts,
        "limit": limit,
        "job_id": job_id,
    }

    try:
        result = JobCommandService(db).trigger_job(action, params)
    except HTTPException as e:
        detail = e.detail if isinstance(e.detail, str) else "任务触发失败"
        return _redirect_with_message("/jobs/run", detail)

    if isinstance(result, CollectJob):
        return _redirect_with_message(f"/jobs/{result.id}", f"任务 #{result.id} 已创建，等待后台执行")
    if isinstance(result, list):
        return _redirect_with_message("/jobs", f"已创建 {len(result)} 个补齐任务")
    if isinstance(result, int) and action in {"manual_backfill_range"}:
        return _redirect_with_message(f"/jobs/{result}", f"任务 #{result} 已创建")
    return _redirect_with_message("/jobs", "任务已创建，等待后台执行")


@router.get("/jobs/{job_id}")
def job_detail_page(
    job_id: int,
    request: Request,
    db: Session = Depends(get_db),
    message: str | None = Query(None),
):
    job = db.get(CollectJob, job_id)
    if not job:
        return RedirectResponse("/jobs", status_code=303)
    query_service = JobQueryService(db)
    logs = query_service.list_job_logs(job_id)
    return templates.TemplateResponse(
        request,
        "job_detail.html",
        _ctx(
            request,
            "jobs",
            job=job,
            message=message,
            logs=logs,
        ),
    )


@router.post("/jobs/delete")
def delete_jobs_form(
    request: Request,
    db: Session = Depends(get_db),
    job_ids: list[int] | None = Form(None),
):
    try:
        deleted = JobCommandService(db).delete_jobs(job_ids or [])
    except HTTPException as e:
        detail = e.detail if isinstance(e.detail, str) else "删除失败"
        return _redirect_with_message("/jobs", detail)
    return _redirect_with_message("/jobs", f"已删除 {deleted} 个任务")


@router.post("/jobs/{job_id}/delete")
def delete_job_form(job_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        JobCommandService(db).delete_jobs([job_id])
    except HTTPException as e:
        detail = e.detail if isinstance(e.detail, str) else "删除失败"
        return _redirect_with_message(f"/jobs/{job_id}", detail)
    return _redirect_with_message("/jobs", f"任务 #{job_id} 已删除")


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
