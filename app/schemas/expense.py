import re
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

PaymentMethod = Literal["cash", "credit_card", "debit_card", "bank_transfer", "e_wallet", "other"]


class ExpenseFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str = Field(default="MYR", min_length=3, max_length=3)
    category_id: UUID
    expense_date: date = Field(default_factory=date.today)
    merchant: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=255)
    payment_method: PaymentMethod | None = None
    notes: str | None = None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", normalized, flags=re.ASCII):
            raise ValueError("Currency must be a three-letter code.")
        return normalized

    @field_validator("merchant", "description", "notes")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class ExpenseCreate(ExpenseFields):
    pass


class ExpenseUpdate(ExpenseFields):
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str = Field(min_length=3, max_length=3)
    category_id: UUID
    expense_date: date


class ExpenseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    category_id: UUID
    category_name: str
    amount: Decimal
    currency: str
    expense_date: date
    merchant: str | None
    description: str | None
    payment_method: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
