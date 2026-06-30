from decimal import Decimal

from app.services.approval_rules import evaluate_credit_flags, quote_requires_approval


def test_quote_requires_approval_when_stock_short():
    assert quote_requires_approval(
        requested_discount=Decimal("5"),
        standard_discount=Decimal("5"),
        requested_qty=50,
        available_qty=30,
        total_amount=Decimal("10000"),
        saleable=True,
        credit_flags=[],
    )


def test_quote_requires_approval_when_discount_exceeds_standard():
    assert quote_requires_approval(
        requested_discount=Decimal("8"),
        standard_discount=Decimal("5"),
        requested_qty=5,
        available_qty=30,
        total_amount=Decimal("10000"),
        saleable=True,
        credit_flags=[],
    )


def test_credit_near_limit_flag():
    assert evaluate_credit_flags(Decimal("80"), Decimal("100")) == ["CUSTOMER_NEAR_CREDIT_LIMIT"]


def test_credit_over_limit_flag():
    assert evaluate_credit_flags(Decimal("120"), Decimal("100")) == ["CUSTOMER_OVER_CREDIT_LIMIT"]
