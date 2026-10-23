from datetime import date, datetime, timezone
from typing import Optional
import uuid

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Column, Float, String

from database import Base


# ==========================================
# SQLAlchemy ORM Model
# ==========================================
class ExpenseDB(Base):
    __tablename__ = "expenses"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(100), nullable=False)
    amount = Column(Float, nullable=False)
    category = Column(String(50), nullable=False)
    date = Column(String(10), nullable=False)
    created_at = Column(
        String(50),
        nullable=False,
        default=lambda: datetime.now(timezone.utc).isoformat(),
    )


# ==========================================
# Pydantic Schemas for Request & Response
# ==========================================
class ExpenseBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=100, description="Title of the expense")
    amount: float = Field(..., gt=0, description="Expense amount in INR (must be positive)")
    category: str = Field(..., min_length=1, max_length=50, description="Expense category")
    date: str = Field(..., description="Date of expense in YYYY-MM-DD format")

    @field_validator("title", "category")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Field cannot be empty or whitespace only")
        return s

    @field_validator("amount")
    @classmethod
    def round_amount(cls, v: float) -> float:
        return round(float(v), 2)

    @field_validator("date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        cleaned = v.strip()
        try:
            date.fromisoformat(cleaned)
            return cleaned
        except ValueError:
            raise ValueError("Date must be in valid YYYY-MM-DD format (e.g., 2026-10-23)")


class ExpenseCreate(ExpenseBase):
    pass


class Expense(ExpenseBase):
    id: str
    created_at: str

    model_config = {"from_attributes": True}


class TotalResponse(BaseModel):
    total: float
    cached: bool
    currency: str = "INR"
    message: Optional[str] = None
