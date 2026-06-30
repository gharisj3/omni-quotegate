from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class CustomerSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: str
    email: str
    credit_limit: Decimal
    current_balance: Decimal
    standard_discount_percent: Decimal
    risk_level: str


class ProductSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    name: str
    category: str
    stock_available: int
    list_price: Decimal
    saleable: bool
    reorder_level: int


class QuoteLineDraftSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    requested_qty: int
    available_qty: int
    quoted_qty: int
    unit_price: Decimal
    line_total: Decimal
    stock_warning: str | None
    product: ProductSchema


class QuoteDraftSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    inquiry_id: int
    customer_id: int
    status: str
    subtotal: Decimal
    discount_percent: Decimal
    discount_amount: Decimal
    total_amount: Decimal
    customer_reply_draft: str
    risk_summary: str
    approval_required: bool
    created_by_ai: bool
    lines: list[QuoteLineDraftSchema]


class ApprovalRequestSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    quote_draft_id: int
    status: str
    reason: str
    risk_flags_json: str
    requested_by: str
    decided_by: str | None
    decision_note: str | None
    created_at: datetime
    decided_at: datetime | None
    quote_draft: QuoteDraftSchema


class InquirySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    raw_message: str
    status: str
    inquiry_type: str | None
    assigned_to: str | None
    estimated_value: Decimal | None
    created_at: datetime
    updated_at: datetime
    customer: CustomerSchema
    quote_draft: QuoteDraftSchema | None


class AuditEventSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entity_type: str
    entity_id: int
    event_type: str
    actor: str
    message: str
    payload_json: str
    created_at: datetime
