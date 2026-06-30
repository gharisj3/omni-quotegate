from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer, Product


@dataclass(slots=True)
class ProductMatch:
    product: Product
    score: int


@dataclass(slots=True)
class CustomerContext:
    customer: Customer
    available_credit: Decimal


@dataclass(slots=True)
class StockCheck:
    product: Product
    requested_qty: int
    available_qty: int
    is_short: bool


class MockERPAdapter:
    """Local adapter that mirrors the shape of a future ERP integration.

    This demo adapter can later be replaced by an Odoo XML-RPC adapter,
    Oracle/Fusion adapter, SAP adapter, or a custom ERP API adapter.
    """

    def __init__(self, db: Session):
        self.db = db

    def search_products(self, query: str) -> list[ProductMatch]:
        tokens = [token.lower() for token in query.replace("-", " ").split() if token]
        results: list[ProductMatch] = []
        for product in self.db.scalars(select(Product)).all():
            haystack = f"{product.sku} {product.name} {product.category}".lower()
            score = sum(12 for token in tokens if token in product.sku.lower())
            score += sum(7 for token in tokens if token in product.name.lower())
            score += sum(3 for token in tokens if token in haystack)
            if score:
                results.append(ProductMatch(product=product, score=score))
        return sorted(results, key=lambda item: item.score, reverse=True)

    def get_customer_context(self, customer_id: int) -> CustomerContext:
        customer = self.db.get(Customer, customer_id)
        if customer is None:
            raise ValueError(f"Customer {customer_id} not found")
        return CustomerContext(
            customer=customer,
            available_credit=Decimal(customer.credit_limit) - Decimal(customer.current_balance),
        )

    def check_stock(self, product_id: int, requested_qty: float) -> StockCheck:
        product = self.db.get(Product, product_id)
        if product is None:
            raise ValueError(f"Product {product_id} not found")
        requested_int = int(requested_qty)
        return StockCheck(
            product=product,
            requested_qty=requested_int,
            available_qty=product.stock_available,
            is_short=requested_int > product.stock_available,
        )
