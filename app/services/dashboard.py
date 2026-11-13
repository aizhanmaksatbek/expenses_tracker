from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from app.models import Category, Expense, User


@dataclass(frozen=True)
class CurrencyTotal:
    currency: str
    amount: Decimal
    daily_average: Decimal


@dataclass(frozen=True)
class CategorySpending:
    name: str
    currency: str
    amount: Decimal
    percentage: float


@dataclass(frozen=True)
class SpendingPeriod:
    label: str
    currency: str
    amount: Decimal


@dataclass(frozen=True)
class TrendPoint:
    label: str
    amount: Decimal
    x: float
    y: float


@dataclass(frozen=True)
class TrendLabel:
    label: str
    position: float
    anchor: str


@dataclass(frozen=True)
class TrendChart:
    currency: str
    line_points: str
    points: list[TrendPoint]
    x_labels: list[TrendLabel]
    y_labels: list[TrendLabel]


@dataclass(frozen=True)
class DashboardStatistics:
    expense_count: int
    totals: list[CurrencyTotal]
    categories: list[CategorySpending]
    trends: list[TrendChart]
    period_label: str


def _build_trend_chart(currency: str, periods: list[SpendingPeriod]) -> TrendChart:
    left, right = 88.0, 688.0
    top, bottom = 16.0, 172.0
    max_amount = max((period.amount for period in periods), default=Decimal("0.00"))
    points = []
    for index, period in enumerate(periods):
        x = left if len(periods) == 1 else left + index * (right - left) / (len(periods) - 1)
        ratio = float(period.amount / max_amount) if max_amount else 0.0
        y = bottom - ratio * (bottom - top)
        points.append(TrendPoint(period.label, period.amount, x, y))

    label_indexes = (
        [0]
        if len(points) == 1
        else [
            round(index * (len(points) - 1) / (min(5, len(points)) - 1))
            for index in range(min(5, len(points)))
        ]
    )
    x_labels = [
        TrendLabel(
            label=points[index].label,
            position=points[index].x,
            anchor="start" if index == 0 else "end" if index == len(points) - 1 else "middle",
        )
        for index in label_indexes
    ]
    y_labels = []
    for fraction in (Decimal(1), Decimal("0.5"), Decimal(0)):
        amount = max_amount * fraction
        position = bottom - float(fraction) * (bottom - top)
        y_labels.append(TrendLabel(f"{amount:,.2f}", position, "end"))

    return TrendChart(
        currency=currency,
        line_points=" ".join(f"{point.x:.2f},{point.y:.2f}" for point in points),
        points=points,
        x_labels=x_labels,
        y_labels=y_labels,
    )


def get_dashboard_statistics(
    db: Session,
    user: User,
    start_date: date,
    end_date: date,
) -> DashboardStatistics:
    filters = (
        Expense.user_id == user.id,
        Expense.expense_date >= start_date,
        Expense.expense_date <= end_date,
    )
    totals_query = db.execute(
        select(
            Expense.currency,
            func.sum(Expense.amount),
            func.count(Expense.id),
        )
        .where(*filters)
        .group_by(Expense.currency)
        .order_by(Expense.currency)
    ).all()
    days_in_period = (end_date - start_date).days + 1
    totals = [
        CurrencyTotal(
            currency=currency,
            amount=amount,
            daily_average=(amount / days_in_period).quantize(Decimal("0.01")),
        )
        for currency, amount, _count in totals_query
    ]

    category_rows = db.execute(
        select(Category.name, Expense.currency, func.sum(Expense.amount))
        .join(Category, Category.id == Expense.category_id)
        .where(*filters)
        .group_by(Category.name, Expense.currency)
        .order_by(Category.name, Expense.currency)
    ).all()
    category_max = defaultdict(Decimal)
    for _name, currency, amount in category_rows:
        category_max[currency] = max(category_max[currency], amount)
    categories = [
        CategorySpending(
            name=name,
            currency=currency,
            amount=amount,
            percentage=float(amount / category_max[currency] * 100),
        )
        for name, currency, amount in category_rows
    ]

    day_count = (end_date - start_date).days
    if day_count <= 30:
        grouping = "day"
        period_rows = db.execute(
            select(Expense.expense_date, Expense.currency, func.sum(Expense.amount))
            .where(*filters)
            .group_by(Expense.expense_date, Expense.currency)
            .order_by(Expense.expense_date, Expense.currency)
        ).all()
        amounts = {
            (expense_date, currency): amount
            for expense_date, currency, amount in period_rows
        }
        bucket_dates = (
            start_date + timedelta(days=offset) for offset in range(day_count + 1)
        )
        labels_and_keys = [
            (bucket_date.strftime("%d %b"), bucket_date)
            for bucket_date in bucket_dates
        ]
    elif day_count <= 730:
        grouping = "month"
        period_rows = db.execute(
            select(
                extract("year", Expense.expense_date),
                extract("month", Expense.expense_date),
                Expense.currency,
                func.sum(Expense.amount),
            )
            .where(*filters)
            .group_by(
                extract("year", Expense.expense_date),
                extract("month", Expense.expense_date),
                Expense.currency,
            )
            .order_by(
                extract("year", Expense.expense_date),
                extract("month", Expense.expense_date),
                Expense.currency,
            )
        ).all()
        amounts = {
            ((int(year), int(month)), currency): amount
            for year, month, currency, amount in period_rows
        }
        bucket_dates = []
        cursor = date(start_date.year, start_date.month, 1)
        last_month = date(end_date.year, end_date.month, 1)
        while cursor <= last_month:
            bucket_dates.append(cursor)
            next_year = cursor.year + (1 if cursor.month == 12 else 0)
            next_month = cursor.month % 12 + 1
            cursor = date(next_year, next_month, 1)
        labels_and_keys = [
            (bucket_date.strftime("%b %Y"), (bucket_date.year, bucket_date.month))
            for bucket_date in bucket_dates
        ]
    else:
        grouping = "year"
        period_rows = db.execute(
            select(
                extract("year", Expense.expense_date),
                Expense.currency,
                func.sum(Expense.amount),
            )
            .where(*filters)
            .group_by(extract("year", Expense.expense_date), Expense.currency)
            .order_by(extract("year", Expense.expense_date), Expense.currency)
        ).all()
        amounts = {
            (int(year), currency): amount for year, currency, amount in period_rows
        }
        labels_and_keys = [
            (str(year), year) for year in range(start_date.year, end_date.year + 1)
        ]

    periods = []
    for label, bucket_key in labels_and_keys:
        for total in totals:
            amount = amounts.get((bucket_key, total.currency), Decimal("0.00"))
            periods.append(
                SpendingPeriod(label=label, currency=total.currency, amount=amount)
            )

    trends = [
        _build_trend_chart(
            total.currency,
            [period for period in periods if period.currency == total.currency],
        )
        for total in totals
    ]

    if grouping == "day":
        period_label = f"{start_date:%b %d, %Y} – {end_date:%b %d, %Y}"
    else:
        period_label = f"{start_date:%b %Y} – {end_date:%b %Y}"

    return DashboardStatistics(
        expense_count=sum(count for _currency, _amount, count in totals_query),
        totals=totals,
        categories=categories,
        trends=trends,
        period_label=period_label,
    )
