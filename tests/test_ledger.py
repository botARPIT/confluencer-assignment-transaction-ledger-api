from decimal import Decimal

import pytest

from app.ledger import resulting_balance


def test_credit_increases_balance() -> None:
    assert resulting_balance(Decimal("100.00"), "credit", Decimal("25.50")) == Decimal("125.50")


def test_debit_decreases_balance() -> None:
    assert resulting_balance(Decimal("100.00"), "debit", Decimal("25.50")) == Decimal("74.50")


def test_exact_balance_debit_is_allowed() -> None:
    assert resulting_balance(Decimal("10.00"), "debit", Decimal("10.00")) == Decimal("0.00")


def test_debit_cannot_overdraw() -> None:
    with pytest.raises(ValueError, match="Insufficient funds"):
        resulting_balance(Decimal("10.00"), "debit", Decimal("10.01"))


def test_amount_must_be_positive() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        resulting_balance(Decimal("10.00"), "credit", Decimal("0.00"))
