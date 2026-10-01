from __future__ import annotations

from decimal import Decimal

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import (
    ApprovalRequest,
    AuditEvent,
    Customer,
    Inquiry,
    Product,
    QuoteDraft,
    QuoteLineDraft,
)
from app.services.audit import write_audit_event


def reset_and_seed(db: Session) -> None:
    for model in [
        ApprovalRequest,
        QuoteLineDraft,
        QuoteDraft,
        AuditEvent,
        Inquiry,
        Product,
        Customer,
    ]:
        db.execute(delete(model))

    customers = [
        Customer(
            name="Al Noor Construction",
            phone="+92-300-1001001",
            email="procurement@alnoor.example.com",
            credit_limit=Decimal(500000),
            current_balance=Decimal(225000),
            standard_discount_percent=Decimal(5),
            risk_level="medium",
        ),
        Customer(
            name="Metro Builders",
            phone="+92-300-1001002",
            email="purchase@metro.example.com",
            credit_limit=Decimal(400000),
            current_balance=Decimal(330000),
            standard_discount_percent=Decimal(4),
            risk_level="elevated",
        ),
        Customer(
            name="Shahid Electric Store",
            phone="+92-300-1001003",
            email="orders@shahid.example.com",
            credit_limit=Decimal(300000),
            current_balance=Decimal(315000),
            standard_discount_percent=Decimal(3),
            risk_level="high",
        ),
        Customer(
            name="Delta Engineering Works",
            phone="+92-300-1001004",
            email="sales@delta.example.com",
            credit_limit=Decimal(700000),
            current_balance=Decimal(150000),
            standard_discount_percent=Decimal(6),
            risk_level="low",
        ),
    ]
    db.add_all(customers)
    db.flush()

    products = [
        Product(
            sku="BDX2200",
            name="Bosch Drill X2200",
            category="Power Tools",
            stock_available=30,
            list_price=Decimal(18500),
            saleable=True,
            reorder_level=10,
        ),
        Product(
            sku="MMC450",
            name="Makita Cutter M450",
            category="Cutting Tools",
            stock_available=18,
            list_price=Decimal(14250),
            saleable=True,
            reorder_level=8,
        ),
        Product(
            sku="SSH100",
            name="Stanley Safety Helmet SH100",
            category="Safety Gear",
            stock_available=120,
            list_price=Decimal(950),
            saleable=True,
            reorder_level=25,
        ),
        Product(
            sku="SBB32",
            name="Schneider Breaker B32",
            category="Electrical",
            stock_available=80,
            list_price=Decimal(4200),
            saleable=True,
            reorder_level=20,
        ),
        Product(
            sku="CR500",
            name="Industrial Cable Roll CR500",
            category="Electrical",
            stock_available=12,
            list_price=Decimal(28500),
            saleable=False,
            reorder_level=15,
        ),
    ]
    db.add_all(products)
    db.flush()

    inquiries = [
        Inquiry(
            source="whatsapp",
            customer_id=customers[0].id,
            raw_message="Do you have 50 units of Bosch Drill X2200 in stock? Can I get a quote with my usual discount?",
            assigned_to="Sara Khan",
        ),
        Inquiry(
            source="email",
            customer_id=customers[3].id,
            raw_message="Need Schneider Breaker B32 availability and can it be delivered this week?",
            assigned_to="Hamza Ali",
        ),
        Inquiry(
            source="chat",
            customer_id=customers[1].id,
            raw_message="Please send a quote for 10 Industrial Cable Roll CR500 units.",
            assigned_to="Sara Khan",
        ),
        Inquiry(
            source="whatsapp",
            customer_id=customers[0].id,
            raw_message="Can you quote 5 Makita Cutter M450 units with 12% discount?",
            assigned_to="Adeel Raza",
        ),
        Inquiry(
            source="email",
            customer_id=customers[2].id,
            raw_message="Share a quote for 20 Bosch Drill X2200 units and let me know stock.",
            assigned_to="Adeel Raza",
        ),
    ]
    db.add_all(inquiries)
    db.flush()

    for inquiry in inquiries:
        write_audit_event(
            db,
            entity_type="inquiry",
            entity_id=inquiry.id,
            event_type="inquiry_created",
            actor="seed_script",
            message=f"Seeded inquiry from {inquiry.source} for customer {inquiry.customer.name}.",
            payload={"inquiry_id": inquiry.id, "customer_id": inquiry.customer_id},
        )

    db.commit()
