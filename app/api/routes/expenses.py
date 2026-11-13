from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app.api.dependencies import AuthContext, DbSession, get_auth_context, require_csrf
from app.models import Expense
from app.schemas.category import CategoryCreate, CategoryResponse
from app.schemas.expense import ExpenseCreate, ExpenseResponse, ExpenseUpdate
from app.services.expenses import (
    create_category,
    create_expense,
    delete_expense,
    get_expense,
    list_categories,
    list_expenses,
    update_expense,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
SortOrder = Literal["newest", "oldest", "amount_asc", "amount_desc"]


def _expense_response(expense: Expense) -> ExpenseResponse:
    return ExpenseResponse(
        id=expense.id,
        user_id=expense.user_id,
        category_id=expense.category_id,
        category_name=expense.category.name,
        amount=expense.amount,
        currency=expense.currency,
        expense_date=expense.expense_date,
        merchant=expense.merchant,
        description=expense.description,
        payment_method=expense.payment_method,
        notes=expense.notes,
        created_at=expense.created_at,
        updated_at=expense.updated_at,
    )


def _form_errors(exc: ValidationError) -> list[str]:
    return [error["msg"] for error in exc.errors()]


def _expense_form(
    request: Request,
    context: AuthContext,
    categories,
    *,
    expense: Expense | None = None,
    errors: list[str] | None = None,
    form_data: dict | None = None,
):
    headers = {}
    if request.headers.get("HX-Request") == "true":
        headers = {
            "HX-Retarget": "#expense-modal .modal-content",
            "HX-Reswap": "outerHTML",
        }
    return templates.TemplateResponse(
        request=request,
        name="expenses/expense_form.html",
        context={
            "csrf_token": context.session.csrf_token,
            "categories": categories,
            "expense": expense,
            "errors": errors or [],
            "form_data": form_data or {},
            "today": date.today(),
        },
        headers=headers,
    )


def _expense_list_fragment(request: Request, db, context: AuthContext) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="expenses/expense_list.html",
        context={
            "expenses": list_expenses(db, context.user),
            "csrf_token": context.session.csrf_token,
        },
    )


@router.get("/categories", response_model=list[CategoryResponse])
def categories(db: DbSession, context: AuthContext = Depends(get_auth_context)):
    return list_categories(db, context.user)


@router.post("/categories", status_code=status.HTTP_201_CREATED)
def add_category(
    category_data: CategoryCreate,
    db: DbSession,
    context: AuthContext = Depends(get_auth_context),
    _csrf: None = Depends(require_csrf),
):
    category = create_category(db, context.user, category_data)
    return CategoryResponse.model_validate(category)


@router.post("/categories/form")
async def add_category_form(
    request: Request,
    db: DbSession,
    context: AuthContext = Depends(get_auth_context),
    _csrf: None = Depends(require_csrf),
):
    form_data = dict(await request.form())
    form_data.pop("csrf_token", None)
    try:
        category_data = CategoryCreate.model_validate(form_data)
        create_category(db, context.user, category_data)
    except (ValidationError, HTTPException) as exc:
        if request.headers.get("HX-Request") != "true":
            return RedirectResponse(
                "/?category_error=invalid", status_code=status.HTTP_303_SEE_OTHER
            )
        errors = _form_errors(exc) if isinstance(exc, ValidationError) else [str(exc.detail)]
        response_status = (
            status.HTTP_422_UNPROCESSABLE_ENTITY
            if isinstance(exc, ValidationError)
            else exc.status_code
        )
        return templates.TemplateResponse(
            request=request,
            name="expenses/category_error.html",
            context={"errors": errors},
            status_code=response_status,
            headers={"HX-Retarget": "#category-errors", "HX-Reswap": "innerHTML"},
        )
    if request.headers.get("HX-Request") != "true":
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request=request,
        name="expenses/category_list.html",
        context={"categories": list_categories(db, context.user)},
        headers={"HX-Trigger": "categoryAdded"},
    )


@router.get("/expenses/new", response_class=HTMLResponse)
def new_expense_page(
    request: Request,
    db: DbSession,
    context: AuthContext = Depends(get_auth_context),
):
    return _expense_form(request, context, list_categories(db, context.user))


@router.get("/expenses/{expense_id}/edit", response_class=HTMLResponse)
def edit_expense_page(
    expense_id: UUID,
    request: Request,
    db: DbSession,
    context: AuthContext = Depends(get_auth_context),
):
    expense = get_expense(db, context.user, expense_id)
    return _expense_form(
        request,
        context,
        list_categories(db, context.user),
        expense=expense,
    )


@router.get("/expenses", response_model=list[ExpenseResponse])
def expenses(
    db: DbSession,
    context: AuthContext = Depends(get_auth_context),
    start_date: date | None = None,
    end_date: date | None = None,
    category_id: UUID | None = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
    sort: SortOrder = "newest",
):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "start_date must be on or before end_date.",
        )
    result = list_expenses(
        db,
        context.user,
        start_date=start_date,
        end_date=end_date,
        category_id=category_id,
        search=search,
        sort=sort,
    )
    return [_expense_response(expense) for expense in result]


@router.post(
    "/expenses",
    response_model=ExpenseResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_expense(
    expense_data: ExpenseCreate,
    db: DbSession,
    context: AuthContext = Depends(get_auth_context),
    _csrf: None = Depends(require_csrf),
):
    expense = create_expense(db, context.user, expense_data)
    return _expense_response(expense)


@router.post("/expenses/form")
async def add_expense_form(
    request: Request,
    db: DbSession,
    context: AuthContext = Depends(get_auth_context),
    _csrf: None = Depends(require_csrf),
):
    data = dict(await request.form())
    data.pop("csrf_token", None)
    try:
        expense_data = ExpenseCreate.model_validate(data)
    except ValidationError as exc:
        return _expense_form(
            request,
            context,
            list_categories(db, context.user),
            errors=_form_errors(exc),
            form_data=data,
        )
    try:
        create_expense(db, context.user, expense_data)
    except HTTPException as exc:
        return _expense_form(
            request,
            context,
            list_categories(db, context.user),
            errors=[str(exc.detail)],
            form_data=data,
        )
    if request.headers.get("HX-Request") == "true":
        fragment = _expense_list_fragment(request, db, context)
        fragment.headers["HX-Trigger"] = "expenseSaved"
        return fragment
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/expenses/{expense_id}", response_model=ExpenseResponse)
def expense(
    expense_id: UUID,
    db: DbSession,
    context: AuthContext = Depends(get_auth_context),
):
    return _expense_response(get_expense(db, context.user, expense_id))


@router.put("/expenses/{expense_id}", response_model=ExpenseResponse)
def edit_expense(
    expense_id: UUID,
    expense_data: ExpenseUpdate,
    db: DbSession,
    context: AuthContext = Depends(get_auth_context),
    _csrf: None = Depends(require_csrf),
):
    expense = update_expense(db, context.user, expense_id, expense_data)
    return _expense_response(expense)


@router.post("/expenses/{expense_id}/edit")
async def edit_expense_form(
    expense_id: UUID,
    request: Request,
    db: DbSession,
    context: AuthContext = Depends(get_auth_context),
    _csrf: None = Depends(require_csrf),
):
    data = dict(await request.form())
    data.pop("csrf_token", None)
    try:
        expense_data = ExpenseUpdate.model_validate(data)
    except ValidationError as exc:
        return _expense_form(
            request,
            context,
            list_categories(db, context.user),
            expense=get_expense(db, context.user, expense_id),
            errors=_form_errors(exc),
            form_data=data,
        )
    try:
        update_expense(db, context.user, expense_id, expense_data)
    except HTTPException as exc:
        return _expense_form(
            request,
            context,
            list_categories(db, context.user),
            expense=get_expense(db, context.user, expense_id),
            errors=[str(exc.detail)],
            form_data=data,
        )
    if request.headers.get("HX-Request") == "true":
        fragment = _expense_list_fragment(request, db, context)
        fragment.headers["HX-Trigger"] = "expenseSaved"
        return fragment
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)


@router.delete(
    "/expenses/{expense_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_expense(
    expense_id: UUID,
    db: DbSession,
    context: AuthContext = Depends(get_auth_context),
    _csrf: None = Depends(require_csrf),
):
    delete_expense(db, context.user, expense_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/expenses/{expense_id}/delete")
def delete_expense_form(
    expense_id: UUID,
    request: Request,
    db: DbSession,
    context: AuthContext = Depends(get_auth_context),
    _csrf: None = Depends(require_csrf),
):
    delete_expense(db, context.user, expense_id)
    if request.headers.get("HX-Request") == "true":
        fragment = _expense_list_fragment(request, db, context)
        fragment.headers["HX-Trigger"] = "expenseSaved"
        return fragment
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
