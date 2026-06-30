from __future__ import annotations

from decimal import Decimal

from app.config import settings


def evaluate_credit_flags(balance: Decimal, credit_limit: Decimal) -> list[str]:
    flags: list[str] = []
    if credit_limit <= 0:
        return ["CUSTOMER_OVER_CREDIT_LIMIT"]
    ratio = balance / credit_limit
    if balance >= credit_limit:
        flags.append("CUSTOMER_OVER_CREDIT_LIMIT")
    elif ratio >= settings.credit_near_limit_ratio:
        flags.append("CUSTOMER_NEAR_CREDIT_LIMIT")
    return flags


def quote_requires_approval(
    *,
    requested_discount: Decimal,
    standard_discount: Decimal,
    requested_qty: int,
    available_qty: int,
    total_amount: Decimal,
    saleable: bool,
    credit_flags: list[str],
) -> bool:
    return any(
        [
            requested_discount > standard_discount,
            requested_qty > available_qty,
            total_amount > settings.high_value_quote_threshold,
            not saleable,
            bool(credit_flags),
        ]
    )
