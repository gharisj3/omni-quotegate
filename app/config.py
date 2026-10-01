from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal


@dataclass(slots=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./omni_quotegate.db")
    currency_code: str = os.getenv("CURRENCY_CODE", "PKR")
    currency_symbol: str = os.getenv("CURRENCY_SYMBOL", "PKR ")
    high_value_quote_threshold: Decimal = Decimal(
        os.getenv("HIGH_VALUE_QUOTE_THRESHOLD", "250000")
    )
    credit_near_limit_ratio: Decimal = Decimal(
        os.getenv("CREDIT_NEAR_LIMIT_RATIO", "0.80")
    )


settings = Settings()


def format_currency(amount: Decimal | float) -> str:
    value = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{settings.currency_symbol}{value:,.2f}"
