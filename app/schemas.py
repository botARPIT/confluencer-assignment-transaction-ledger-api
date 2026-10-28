from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, from_attributes=True)


class AccountCreate(StrictModel):
    name: str = Field(min_length=1, max_length=120)


class AccountRead(StrictModel):
    id: UUID
    name: str
    balance: Decimal
    created_at: datetime


class AccountBalanceRead(StrictModel):
    account_id: UUID
    balance: Decimal


class TransactionCreate(StrictModel):
    type: Literal["credit", "debit"]
    amount: Decimal = Field(gt=Decimal("0"), max_digits=12, decimal_places=2, strict=False)
    description: str = Field(min_length=1, max_length=500)
    reference_id: str = Field(min_length=1, max_length=100)


class TransactionRead(StrictModel):
    id: UUID
    account_id: UUID
    type: Literal["credit", "debit"]
    amount: Decimal
    description: str
    reference_id: str
    created_at: datetime


class TransactionHistoryRead(StrictModel):
    transactions: list[TransactionRead]
    page: int
    limit: int
    total_records: int
    total_pages: int


class TransferCreate(StrictModel):
    source_account_id: UUID
    destination_account_id: UUID
    amount: Decimal = Field(gt=Decimal("0"), max_digits=12, decimal_places=2, strict=False)
    description: str = Field(min_length=1, max_length=500)
    reference_id: str = Field(min_length=1, max_length=100)


class TransferRead(StrictModel):
    source_account_id: UUID
    destination_account_id: UUID
    amount: Decimal
    reference_id: str
    source_transaction_id: UUID
    destination_transaction_id: UUID
    source_balance: Decimal
    destination_balance: Decimal
