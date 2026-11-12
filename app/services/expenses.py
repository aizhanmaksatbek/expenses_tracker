from datetime import date
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models import Category, Expense, User
from app.schemas.category import CategoryCreate
from app.schemas.expense import ExpenseCreate, ExpenseUpdate

DEFAULT_CATEGORIES = ("Food", "Transport", "Housing", "Utilities", "Health", "Shopping", "Other")


def list_categories(db: Session, user: User) -> list[Category]:
    return list(
        db.scalars(
            select(Category).where(Category.user_id == user.id).order_by(Category.name)
        ).all()
    )


def create_category(db: Session, user: User, data: CategoryCreate) -> Category:
    category = Category(user_id=user.id, name=data.name)
    db.add(category)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "A category with this name already exists."
        ) from None
    db.refresh(category)
    return category


def list_expenses(
    db: Session,
    user: User,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    category_id: UUID | None = None,
    search: str | None = None,
    sort: str = "newest",
) -> list[Expense]:
    statement = (
        select(Expense).options(joinedload(Expense.category)).where(Expense.user_id == user.id)
    )
    if start_date:
        statement = statement.where(Expense.expense_date >= start_date)
    if end_date:
        statement = statement.where(Expense.expense_date <= end_date)
    if category_id:
        statement = statement.where(Expense.category_id == category_id)
    if search:
        pattern = f"%{search.strip()}%"
        statement = statement.where(
            or_(
                Expense.merchant.ilike(pattern),
                Expense.description.ilike(pattern),
                Expense.notes.ilike(pattern),
            )
        )
    if sort == "oldest":
        statement = statement.order_by(Expense.expense_date.asc(), Expense.created_at.asc())
    elif sort == "amount_asc":
        statement = statement.order_by(Expense.amount.asc(), Expense.expense_date.desc())
    elif sort == "amount_desc":
        statement = statement.order_by(Expense.amount.desc(), Expense.expense_date.desc())
    else:
        statement = statement.order_by(Expense.expense_date.desc(), Expense.created_at.desc())
    return list(db.scalars(statement).all())


def get_expense(db: Session, user: User, expense_id: UUID) -> Expense:
    expense = db.scalar(
        select(Expense)
        .options(joinedload(Expense.category))
        .where(Expense.id == expense_id, Expense.user_id == user.id)
    )
    if expense is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Expense not found.")
    return expense


def _validate_category(db: Session, user: User, category_id: UUID) -> None:
    category = db.scalar(
        select(Category.id).where(Category.id == category_id, Category.user_id == user.id)
    )
    if category is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid category.")


def _save(db: Session, user: User, expense: Expense) -> Expense:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Expense could not be saved.") from None
    db.refresh(expense)
    return get_expense(db, user, expense.id)


def create_expense(db: Session, user: User, data: ExpenseCreate) -> Expense:
    _validate_category(db, user, data.category_id)
    expense = Expense(user_id=user.id, **data.model_dump())
    db.add(expense)
    return _save(db, user, expense)


def update_expense(db: Session, user: User, expense_id: UUID, data: ExpenseUpdate) -> Expense:
    expense = get_expense(db, user, expense_id)
    _validate_category(db, user, data.category_id)
    for field, value in data.model_dump().items():
        setattr(expense, field, value)
    return _save(db, user, expense)


def delete_expense(db: Session, user: User, expense_id: UUID) -> None:
    expense = get_expense(db, user, expense_id)
    db.delete(expense)
    db.commit()
