"""Create a demo user with sample expenses and budgets.

Usage: python -m app.scripts.seed
"""

import random
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Budget, Category, Expense, User
from app.security.passwords import hash_password
from app.services.expenses import DEFAULT_CATEGORIES

DEMO_USERNAME = "demo"
DEMO_PASSWORD = "DemoPassword123!"
MERCHANTS = {
    "Food": ["Village Grocer", "Nasi Kandar", "Starbucks"],
    "Transport": ["Grab", "Shell", "Touch 'n Go"],
    "Housing": ["Rent", "TNB Electricity", "Unifi"],
}


def seed() -> None:
    rng = random.Random(42)
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.username == DEMO_USERNAME)):
            print("Demo user already exists.")
            return
        user = User(
            username=DEMO_USERNAME,
            email="demo@example.com",
            password_hash=hash_password(DEMO_PASSWORD),
        )
        db.add(user)
        db.flush()
        categories = [Category(user_id=user.id, name=name) for name in DEFAULT_CATEGORIES]
        db.add_all(categories)
        db.flush()
        today = date.today()
        for offset in range(90):
            day = today - timedelta(days=offset)
            for category in rng.sample(categories, k=rng.randint(0, 2)):
                merchants = MERCHANTS.get(category.name, [category.name])
                db.add(
                    Expense(
                        user_id=user.id,
                        category_id=category.id,
                        amount=Decimal(rng.randint(500, 15000)) / 100,
                        currency="MYR",
                        expense_date=day,
                        merchant=rng.choice(merchants),
                    )
                )
        for category in categories[:3]:
            db.add(
                Budget(
                    user_id=user.id,
                    category_id=category.id,
                    currency="MYR",
                    amount=Decimal("300.00"),
                )
            )
        db.commit()
        print(f"Created demo user '{DEMO_USERNAME}' with password '{DEMO_PASSWORD}'.")


if __name__ == "__main__":
    seed()
