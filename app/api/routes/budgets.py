from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import APIRouter, Depends, Form
from fastapi.responses import RedirectResponse

from app.api.dependencies import AuthContext, DbSession, get_auth_context, require_csrf
from app.services.budgets import delete_budget, set_budget

router = APIRouter()


@router.post("/budgets")
def save_budget(
    db: DbSession,
    category_id: UUID = Form(),
    amount: str = Form(),
    currency: str = Form("MYR"),
    context: AuthContext = Depends(get_auth_context),
    _csrf: None = Depends(require_csrf),
):
    currency = currency.upper()
    try:
        value = Decimal(amount).quantize(Decimal("0.01"))
    except InvalidOperation:
        return RedirectResponse("/?budget_error=invalid", status_code=303)
    valid_currency = len(currency) == 3 and currency.isalpha()
    if value <= 0 or value >= Decimal("10000000") or not valid_currency:
        return RedirectResponse("/?budget_error=invalid", status_code=303)
    if set_budget(db, context.user, category_id, currency, value) is None:
        return RedirectResponse("/?budget_error=invalid", status_code=303)
    return RedirectResponse("/", status_code=303)


@router.post("/budgets/{budget_id}/delete")
def remove_budget(
    budget_id: UUID,
    db: DbSession,
    context: AuthContext = Depends(get_auth_context),
    _csrf: None = Depends(require_csrf),
):
    delete_budget(db, context.user, budget_id)
    return RedirectResponse("/", status_code=303)

