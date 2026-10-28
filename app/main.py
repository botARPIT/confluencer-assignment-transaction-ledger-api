from decimal import Decimal
from math import ceil
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.ledger import resulting_balance
from app.models import Account, LedgerTransaction
from app.schemas import (
    AccountBalanceRead,
    AccountCreate,
    AccountRead,
    TransactionCreate,
    TransactionHistoryRead,
    TransactionRead,
    TransferCreate,
    TransferRead,
)

app = FastAPI(title="Confluencer Transaction Ledger", version="1.0.0", description="Account balances and transaction history.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["null", "http://localhost:8000", "http://127.0.0.1:8000"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def home() -> RedirectResponse:
    return RedirectResponse(url="/ui/", status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@app.post("/accounts", response_model=AccountRead, status_code=status.HTTP_201_CREATED, tags=["accounts"])
def create_account(payload: AccountCreate, db: Session = Depends(get_db)) -> Account:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Name must not be blank")
    account = Account(id=uuid4(), name=name, balance=Decimal("0.00"))
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@app.get("/accounts/{account_id}", response_model=AccountBalanceRead, tags=["accounts"])
def get_account(account_id: UUID, db: Session = Depends(get_db)) -> AccountBalanceRead:
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return AccountBalanceRead(account_id=account.id, balance=account.balance)


@app.post("/accounts/{account_id}/transactions", response_model=TransactionRead, status_code=status.HTTP_201_CREATED, tags=["transactions"])
def create_transaction(account_id: UUID, payload: TransactionCreate, db: Session = Depends(get_db)) -> LedgerTransaction:
    account = db.scalar(select(Account).where(Account.id == account_id).with_for_update())
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    existing = db.scalar(select(LedgerTransaction).where(
        LedgerTransaction.account_id == account_id,
        LedgerTransaction.reference_id == payload.reference_id,
    ))
    if existing is not None:
        raise HTTPException(status_code=409, detail="reference_id already exists for this account")
    try:
        updated_balance = resulting_balance(account.balance, payload.type, payload.amount)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    account.balance = updated_balance
    transaction = LedgerTransaction(
        id=uuid4(), account_id=account_id, type=payload.type, amount=payload.amount,
        description=payload.description.strip(), reference_id=payload.reference_id,
    )
    if not transaction.description:
        raise HTTPException(status_code=422, detail="Description must not be blank")
    db.add(transaction)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Transaction conflicts with an existing ledger entry") from exc
    db.refresh(transaction)
    return transaction


@app.get("/accounts/{account_id}/transactions", response_model=TransactionHistoryRead, tags=["transactions"])
def list_transactions(
    account_id: UUID,
    transaction_type: str | None = Query(default=None, alias="type", pattern="^(credit|debit)$"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> TransactionHistoryRead:
    if db.get(Account, account_id) is None:
        raise HTTPException(status_code=404, detail="Account not found")
    filters = [LedgerTransaction.account_id == account_id]
    if transaction_type is not None:
        filters.append(LedgerTransaction.type == transaction_type)
    total_records = db.scalar(select(func.count()).select_from(LedgerTransaction).where(*filters)) or 0
    statement = (
        select(LedgerTransaction)
        .where(*filters)
        .order_by(LedgerTransaction.created_at.desc(), LedgerTransaction.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    transactions = list(db.scalars(statement).all())
    return TransactionHistoryRead(
        transactions=transactions,
        page=page,
        limit=limit,
        total_records=total_records,
        total_pages=ceil(total_records / limit),
    )


@app.post("/transfers", response_model=TransferRead, status_code=status.HTTP_201_CREATED, tags=["transfers"])
def transfer_funds(payload: TransferCreate, db: Session = Depends(get_db)) -> TransferRead:
    if payload.source_account_id == payload.destination_account_id:
        raise HTTPException(status_code=422, detail="Source and destination accounts must differ")

    accounts = db.scalars(
        select(Account)
        .where(Account.id.in_([payload.source_account_id, payload.destination_account_id]))
        .order_by(Account.id)
        .with_for_update()
    ).all()
    account_by_id = {account.id: account for account in accounts}
    source = account_by_id.get(payload.source_account_id)
    destination = account_by_id.get(payload.destination_account_id)
    if source is None or destination is None:
        raise HTTPException(status_code=404, detail="Account not found")

    existing = db.scalar(
        select(LedgerTransaction.id).where(
            LedgerTransaction.account_id.in_([payload.source_account_id, payload.destination_account_id]),
            LedgerTransaction.reference_id == payload.reference_id,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="reference_id already exists for one of these accounts")

    try:
        source_balance = resulting_balance(source.balance, "debit", payload.amount)
        destination_balance = resulting_balance(destination.balance, "credit", payload.amount)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    description = payload.description.strip()
    if not description:
        raise HTTPException(status_code=422, detail="Description must not be blank")
    source_transaction = LedgerTransaction(
        id=uuid4(), account=source, type="debit", amount=payload.amount,
        description=description, reference_id=payload.reference_id,
    )
    destination_transaction = LedgerTransaction(
        id=uuid4(), account=destination, type="credit", amount=payload.amount,
        description=description, reference_id=payload.reference_id,
    )
    source.balance = source_balance
    destination.balance = destination_balance
    db.add_all([source_transaction, destination_transaction])
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Transfer conflicts with an existing ledger entry") from exc

    return TransferRead(
        source_account_id=source.id,
        destination_account_id=destination.id,
        amount=payload.amount,
        reference_id=payload.reference_id,
        source_transaction_id=source_transaction.id,
        destination_transaction_id=destination_transaction.id,
        source_balance=source.balance,
        destination_balance=destination.balance,
    )


app.mount("/ui", StaticFiles(directory="static", html=True), name="ui")
