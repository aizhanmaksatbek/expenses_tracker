from datetime import date

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.api.dependencies import DbSession, get_auth_context
from app.api.routes.auth import router as auth_router
from app.api.routes.expenses import router as expense_router
from app.services.dashboard import get_dashboard_statistics
from app.services.expenses import list_categories, list_expenses

templates = Jinja2Templates(directory="app/templates")

app = FastAPI(title="Personal Expense Tracker")
app.include_router(auth_router)
app.include_router(expense_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    db: DbSession,
    start_date: date | None = None,
    end_date: date | None = None,
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
            "start_date": selected_start,
            "end_date": selected_end,
        },
    )
