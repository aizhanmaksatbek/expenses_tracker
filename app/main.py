from datetime import date, timedelta

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from app.api.dependencies import DbSession, get_auth_context
from app.api.routes.auth import router as auth_router
from app.api.routes.budgets import router as budget_router
from app.api.routes.expenses import router as expense_router
from app.services.budgets import list_budget_progress
from app.services.dashboard import get_dashboard_statistics
from app.services.expenses import list_categories, list_expenses

templates = Jinja2Templates(directory="app/templates")

app = FastAPI(title="Personal Expense Tracker")
app.include_router(auth_router)
app.include_router(expense_router)
app.include_router(budget_router)


@app.get("/health")
def health(db: DbSession) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database unavailable.") from None
    return {"status": "ok"}


def _preset_range(preset: str | None, today: date) -> tuple[date, date] | None:
    first = today.replace(day=1)
    if preset == "this_month":
        return first, today
    if preset == "last_month":
        end = first - timedelta(days=1)
        return end.replace(day=1), end
    if preset == "last_30":
        return today - timedelta(days=29), today
    if preset == "ytd":
        return today.replace(month=1, day=1), today
    if preset == "last_12":
        return today - timedelta(days=364), today
    return None


@app.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    db: DbSession,
    start_date: date | None = None,
    end_date: date | None = None,
    preset: str | None = None,
):
    try:
        context = get_auth_context(request, db)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        raise
    today = date.today()
    selected_start = start_date or today.replace(day=1)
    selected_end = end_date or today
    active_preset = preset if _preset_range(preset, today) else None
    if active_preset:
        selected_start, selected_end = _preset_range(preset, today)
    if selected_start > selected_end:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "start_date must be on or before end_date.",
        )
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "user": context.user,
            "csrf_token": context.session.csrf_token,
            "expenses": list_expenses(db, context.user),
            "categories": list_categories(db, context.user),
            "statistics": get_dashboard_statistics(
                db, context.user, selected_start, selected_end
            ),
            "budgets": list_budget_progress(db, context.user, selected_end),
            "preset": active_preset,
            "start_date": selected_start,
            "end_date": selected_end,
        },
    )
