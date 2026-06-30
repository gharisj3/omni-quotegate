from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import format_currency
from app.models import ApprovalRequest, Inquiry, Product, QuoteDraft, QuoteLineDraft
from app.services.approval_rules import evaluate_credit_flags, quote_requires_approval
from app.services.audit import write_audit_event
from app.services.mock_erp import MockERPAdapter


@dataclass(slots=True)
class InquiryClassification:
    inquiry_type: str
    requested_qty: int
    requested_discount: Decimal
    wants_delivery: bool
    product_query: str


@dataclass(slots=True)
class QuoteProposal:
    quote_draft: QuoteDraft
    approval_request: ApprovalRequest | None
    risk_flags: list[str]
    matched_product: Product | None


class AIQuoteEngine:
    def __init__(self, db: Session):
        self.db = db
        self.erp = MockERPAdapter(db)

    def classify_inquiry(self, inquiry: Inquiry) -> InquiryClassification:
        message = inquiry.raw_message.lower()
        inquiry_type = "quote_request"
        if "available" in message or "stock" in message:
            inquiry_type = "availability_check"
        if "quote" in message:
            inquiry_type = "quote_request"
        if "discount" in message:
            inquiry_type = "discount_review"

        qty_match = re.search(r"(\d+)\s+units?", message)
        requested_qty = int(qty_match.group(1)) if qty_match else 1

        discount_match = re.search(r"(\d+)\s*%\s*discount", message)
        requested_discount = Decimal(discount_match.group(1)) if discount_match else Decimal("0")
        if "usual discount" in message or "my usual discount" in message:
            customer = inquiry.customer
            requested_discount = Decimal(customer.standard_discount_percent)

        cleaned_query = re.sub(r"[^a-zA-Z0-9 ]", " ", inquiry.raw_message)
        wants_delivery = "deliver" in message or "delivery" in message
        return InquiryClassification(
            inquiry_type=inquiry_type,
            requested_qty=requested_qty,
            requested_discount=requested_discount,
            wants_delivery=wants_delivery,
            product_query=cleaned_query,
        )

    def lookup_product(self, product_query: str) -> Product | None:
        matches = self.erp.search_products(product_query)
        return matches[0].product if matches else None

    def lookup_customer(self, customer_id: int):
        return self.erp.get_customer_context(customer_id)

    def propose_quote(self, inquiry: Inquiry) -> QuoteProposal:
        classification = self.classify_inquiry(inquiry)
        inquiry.inquiry_type = classification.inquiry_type
        inquiry.status = "analyzed"

        matched_product = self.lookup_product(classification.product_query)
        customer_context = self.lookup_customer(inquiry.customer_id)
        customer = customer_context.customer

        write_audit_event(
            self.db,
            entity_type="inquiry",
            entity_id=inquiry.id,
            event_type="inquiry_analyzed",
            actor="ai_engine",
            message=f"Inquiry classified as {classification.inquiry_type}.",
            payload={
                "inquiry_id": inquiry.id,
                "inquiry_type": classification.inquiry_type,
                "requested_qty": classification.requested_qty,
            },
        )
        write_audit_event(
            self.db,
            entity_type="customer",
            entity_id=customer.id,
            event_type="customer_context_checked",
            actor="ai_engine",
            message=f"Customer credit context reviewed for {customer.name}.",
            payload={
                "customer_id": customer.id,
                "credit_limit": str(customer.credit_limit),
                "current_balance": str(customer.current_balance),
                "available_credit": str(customer_context.available_credit),
            },
        )

        risk_flags: list[str] = []
        requested_discount = classification.requested_discount
        if requested_discount == 0:
            requested_discount = Decimal(customer.standard_discount_percent)

        subtotal = Decimal("0.00")
        lines: list[QuoteLineDraft] = []
        reason_parts: list[str] = []

        if matched_product:
            stock_check = self.erp.check_stock(matched_product.id, classification.requested_qty)
            if stock_check.available_qty == 0:
                risk_flags.append("OUT_OF_STOCK")
            elif stock_check.is_short:
                risk_flags.append("LOW_STOCK")

            if not matched_product.saleable:
                risk_flags.append("MANUAL_PRICE_REVIEW")

            quoted_qty = min(classification.requested_qty, stock_check.available_qty)
            unit_price = Decimal(matched_product.list_price)
            line_total = (unit_price * quoted_qty).quantize(Decimal("0.01"))
            subtotal += line_total
            lines.append(
                QuoteLineDraft(
                    product_id=matched_product.id,
                    requested_qty=classification.requested_qty,
                    available_qty=stock_check.available_qty,
                    quoted_qty=quoted_qty,
                    unit_price=unit_price,
                    line_total=line_total,
                    stock_warning=(
                        f"Only {stock_check.available_qty} available"
                        if stock_check.is_short
                        else None
                    ),
                )
            )
            write_audit_event(
                self.db,
                entity_type="product",
                entity_id=matched_product.id,
                event_type="product_matched",
                actor="ai_engine",
                message=f"Matched inquiry to product {matched_product.name}.",
                payload={
                    "inquiry_id": inquiry.id,
                    "product_id": matched_product.id,
                    "requested_qty": classification.requested_qty,
                    "available_qty": stock_check.available_qty,
                },
            )
        else:
            risk_flags.append("MANUAL_PRICE_REVIEW")
            reason_parts.append("product match review")

        if requested_discount > Decimal(customer.standard_discount_percent):
            risk_flags.append("DISCOUNT_ABOVE_STANDARD")

        credit_flags = evaluate_credit_flags(
            Decimal(customer.current_balance), Decimal(customer.credit_limit)
        )
        risk_flags.extend(credit_flags)

        total_before_discount = subtotal
        discount_amount = (
            total_before_discount * requested_discount / Decimal("100")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total_amount = (total_before_discount - discount_amount).quantize(Decimal("0.01"))
        inquiry.estimated_value = total_amount

        if matched_product:
            approval_required = quote_requires_approval(
                requested_discount=requested_discount,
                standard_discount=Decimal(customer.standard_discount_percent),
                requested_qty=classification.requested_qty,
                available_qty=matched_product.stock_available,
                total_amount=total_amount,
                saleable=matched_product.saleable,
                credit_flags=credit_flags,
            )
        else:
            approval_required = True

        if requested_discount > Decimal(customer.standard_discount_percent):
            reason_parts.append("discount review")
        if matched_product and classification.requested_qty > matched_product.stock_available:
            reason_parts.append("stock review")
        if credit_flags:
            reason_parts.append("credit review")
        if matched_product and not matched_product.saleable:
            reason_parts.append("saleability review")
        if total_amount > Decimal("250000"):
            reason_parts.append("high value review")

        risk_summary = ", ".join(risk_flags) if risk_flags else "No material risk flags."
        if matched_product:
            availability_sentence = (
                f"We found {matched_product.name} with {matched_product.stock_available} units currently available out of {classification.requested_qty} requested."
            )
        else:
            availability_sentence = "We could not confidently match a saleable product from the inquiry."
        approval_sentence = (
            f" This quote requires internal approval due to {' and '.join(dict.fromkeys(reason_parts))}."
            if approval_required
            else " This quote is ready for sales rep review."
        )
        reply_draft = (
            "Thanks for your inquiry. "
            f"{availability_sentence} "
            f"The estimated quote total is {format_currency(total_amount)}."
            f"{approval_sentence}"
        )

        quote_draft = inquiry.quote_draft or QuoteDraft(inquiry_id=inquiry.id, customer_id=customer.id)
        quote_draft.status = "pending_approval" if approval_required else "drafted"
        quote_draft.subtotal = subtotal
        quote_draft.discount_percent = requested_discount
        quote_draft.discount_amount = discount_amount
        quote_draft.total_amount = total_amount
        quote_draft.customer_reply_draft = reply_draft
        quote_draft.risk_summary = risk_summary
        quote_draft.approval_required = approval_required
        quote_draft.created_by_ai = True
        quote_draft.lines.clear()
        for line in lines:
            quote_draft.lines.append(line)
        self.db.add(quote_draft)
        self.db.flush()

        inquiry.status = "approval_pending" if approval_required else "quote_drafted"

        write_audit_event(
            self.db,
            entity_type="quote_draft",
            entity_id=quote_draft.id,
            event_type="quote_drafted",
            actor="ai_engine",
            message=f"Quote draft created for inquiry {inquiry.id}.",
            payload={
                "quote_draft_id": quote_draft.id,
                "inquiry_id": inquiry.id,
                "total_amount": str(total_amount),
                "risk_flags": risk_flags,
            },
        )

        approval_request = quote_draft.approval_request
        if approval_required:
            approval_request = approval_request or ApprovalRequest(
                quote_draft_id=quote_draft.id,
                requested_by="ai_engine",
            )
            approval_request.status = "pending"
            approval_request.reason = ", ".join(dict.fromkeys(reason_parts)) or "manual review"
            approval_request.risk_flags_json = ",".join(risk_flags)
            self.db.add(approval_request)
            self.db.flush()
            write_audit_event(
                self.db,
                entity_type="approval_request",
                entity_id=approval_request.id,
                event_type="approval_requested",
                actor="ai_engine",
                message=f"Approval requested for quote draft {quote_draft.id}.",
                payload={
                    "approval_request_id": approval_request.id,
                    "quote_draft_id": quote_draft.id,
                    "risk_flags": risk_flags,
                },
            )

        return QuoteProposal(
            quote_draft=quote_draft,
            approval_request=approval_request,
            risk_flags=risk_flags,
            matched_product=matched_product,
        )


def analyze_inquiry(db: Session, inquiry_id: int) -> Inquiry:
    inquiry = db.scalars(select(Inquiry).where(Inquiry.id == inquiry_id)).first()
    if inquiry is None:
        raise ValueError("Inquiry not found")
    engine = AIQuoteEngine(db)
    classification = engine.classify_inquiry(inquiry)
    matched_product = engine.lookup_product(classification.product_query)
    engine.lookup_customer(inquiry.customer_id)
    inquiry.inquiry_type = classification.inquiry_type
    inquiry.status = "analyzed"
    if matched_product:
        inquiry.estimated_value = Decimal(matched_product.list_price) * classification.requested_qty
        write_audit_event(
            db,
            entity_type="product",
            entity_id=matched_product.id,
            event_type="product_matched",
            actor="ai_engine",
            message=f"Matched inquiry to product {matched_product.name}.",
            payload={"inquiry_id": inquiry.id, "product_id": matched_product.id},
        )
    write_audit_event(
        db,
        entity_type="inquiry",
        entity_id=inquiry.id,
        event_type="inquiry_analyzed",
        actor="ai_engine",
        message=f"Inquiry classified as {classification.inquiry_type}.",
        payload={
            "inquiry_id": inquiry.id,
            "inquiry_type": classification.inquiry_type,
            "requested_qty": classification.requested_qty,
        },
    )
    db.flush()
    return inquiry
