from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.api.dependencies import DbSession, get_auth_context
from app.api.routes.auth import router as auth_router
from app.api.routes.expenses import router as expense_router
from app.services.expenses import list_categories, list_expenses

templates = Jinja2Templates(directory="app/templates")

app = FastAPI(title="Personal Expense Tracker")
app.include_router(auth_router)
app.include_router(expense_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: DbSession):
    try:
        context = get_auth_context(request, db)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        raise
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "user": context.user,
            "csrf_token": context.session.csrf_token,
            "expenses": list_expenses(db, context.user),
            "categories": list_categories(db, context.user),
        },
    )
