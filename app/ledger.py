from decimal import Decimal
from typing import Literal


TransactionType = Literal["credit", "debit"]


def resulting_balance(balance: Decimal, transaction_type: TransactionType, amount: Decimal) -> Decimal:
    """Return the balance after a valid positive-amount transaction."""
    if amount <= 0:
        raise ValueError("Amount must be greater than zero")
    new_balance = balance + amount if transaction_type == "credit" else balance - amount
    if new_balance < 0:
        raise ValueError("Insufficient funds")
    return new_balance
