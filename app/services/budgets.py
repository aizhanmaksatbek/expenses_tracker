from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models import Budget, Category, Expense, User


@dataclass(frozen=True)
class BudgetProgress:
    category: str
    currency: str
    limit: Decimal
    spent: Decimal
    percent: float
    over: bool
    near: bool


def set_budget(
    db: Session, user: User, category_id: UUID, currency: str, amount: Decimal
) -> Budget | None:
    """Create or update a budget. Returns None if the category is not owned by the user."""
    category = db.scalar(
        select(Category).where(Category.id == category_id, Category.user_id == user.id)
    )
    if category is None:
        return None
    budget = db.scalar(
        select(Budget).where(
            Budget.user_id == user.id,
            Budget.category_id == category_id,
            Budget.currency == currency,
        )
    )
    if budget is None:
        budget = Budget(user_id=user.id, category_id=category_id, currency=currency, amount=amount)
        db.add(budget)
    else:
        budget.amount = amount
    db.commit()
    return budget


def delete_budget(db: Session, user: User, budget_id: UUID) -> None:
    budget = db.scalar(select(Budget).where(Budget.id == budget_id, Budget.user_id == user.id))
    if budget is not None:
        db.delete(budget)
        db.commit()


def list_budget_progress(
    db: Session, user: User, month: date
) -> list[tuple[Budget, BudgetProgress]]:
    month_start = month.replace(day=1)
    next_month = (
        date(month_start.year + 1, 1, 1)
        if month_start.month == 12
        else date(month_start.year, month_start.month + 1, 1)
    )
    budgets = db.scalars(
        select(Budget).options(joinedload(Budget.category)).where(Budget.user_id == user.id)
    ).all()
    spent_rows = db.execute(
        select(Expense.category_id, Expense.currency, func.sum(Expense.amount))
        .where(
            Expense.user_id == user.id,
            Expense.expense_date >= month_start,
            Expense.expense_date < next_month,
        )
        .group_by(Expense.category_id, Expense.currency)
    ).all()
    spent = {(category_id, currency): amount for category_id, currency, amount in spent_rows}
    result = []
    for budget in sorted(budgets, key=lambda item: item.category.name):
        used = spent.get((budget.category_id, budget.currency), Decimal("0.00"))
        ratio = float(used / budget.amount * 100)
        result.append(
            (
                budget,
                BudgetProgress(
                    category=budget.category.name,
                    currency=budget.currency,
                    limit=budget.amount,
                    spent=used,
                    percent=min(ratio, 100.0),
                    over=ratio > 100,
                    near=80 <= ratio <= 100,
                ),
            )
        )
    return result
