from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import ApprovalRequest, AuditEvent, Inquiry, QuoteDraft, QuoteLineDraft
from app.schemas import ApprovalRequestSchema, AuditEventSchema, InquirySchema
from app.services.ai_quote_engine import AIQuoteEngine, analyze_inquiry
from app.services.audit import write_audit_event

router = APIRouter(prefix="/api/v1", tags=["api"])


def get_inquiry_or_404(db: Session, inquiry_id: int) -> Inquiry:
    inquiry = (
        db.scalars(
            select(Inquiry)
            .where(Inquiry.id == inquiry_id)
            .options(
                joinedload(Inquiry.customer),
                joinedload(Inquiry.quote_draft).joinedload(QuoteDraft.lines).joinedload(QuoteLineDraft.product),
            )
        ).first()
    )
    if inquiry is None:
        raise HTTPException(status_code=404, detail="Inquiry not found")
    return inquiry


def get_approval_or_404(db: Session, approval_id: int) -> ApprovalRequest:
    approval = (
        db.scalars(
            select(ApprovalRequest)
            .where(ApprovalRequest.id == approval_id)
            .options(
                joinedload(ApprovalRequest.quote_draft)
                .joinedload(QuoteDraft.inquiry),
                joinedload(ApprovalRequest.quote_draft).joinedload(QuoteDraft.customer),
                joinedload(ApprovalRequest.quote_draft).joinedload(QuoteDraft.lines).joinedload(QuoteLineDraft.product),
            )
        ).first()
    )
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return approval


@router.get("/inquiries", response_model=list[InquirySchema])
def list_inquiries(db: Session = Depends(get_db)):
    inquiries = db.scalars(
        select(Inquiry)
        .order_by(desc(Inquiry.created_at))
        .options(
            joinedload(Inquiry.customer),
            joinedload(Inquiry.quote_draft).joinedload(QuoteDraft.lines).joinedload(QuoteLineDraft.product),
        )
    ).unique().all()
    return inquiries


@router.get("/inquiries/{inquiry_id}", response_model=InquirySchema)
def get_inquiry(inquiry_id: int, db: Session = Depends(get_db)):
    return get_inquiry_or_404(db, inquiry_id)


@router.post("/inquiries/{inquiry_id}/analyze", response_model=InquirySchema)
def analyze_inquiry_endpoint(inquiry_id: int, db: Session = Depends(get_db)):
    try:
        inquiry = analyze_inquiry(db, inquiry_id)
        db.commit()
        db.refresh(inquiry)
        return get_inquiry_or_404(db, inquiry_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/inquiries/{inquiry_id}/draft-quote", response_model=InquirySchema)
def draft_quote(inquiry_id: int, db: Session = Depends(get_db)):
    inquiry = get_inquiry_or_404(db, inquiry_id)
    engine = AIQuoteEngine(db)
    engine.propose_quote(inquiry)
    db.commit()
    return get_inquiry_or_404(db, inquiry_id)


@router.get("/approvals", response_model=list[ApprovalRequestSchema])
def list_approvals(db: Session = Depends(get_db)):
    approvals = db.scalars(
        select(ApprovalRequest)
        .order_by(desc(ApprovalRequest.created_at))
        .options(
            joinedload(ApprovalRequest.quote_draft).joinedload(QuoteDraft.customer),
            joinedload(ApprovalRequest.quote_draft).joinedload(QuoteDraft.inquiry),
            joinedload(ApprovalRequest.quote_draft).joinedload(QuoteDraft.lines).joinedload(QuoteLineDraft.product),
        )
    ).unique().all()
    return approvals


def _decide_approval(db: Session, approval_id: int, approved: bool) -> ApprovalRequest:
    approval = get_approval_or_404(db, approval_id)
    approval.status = "approved" if approved else "rejected"
    approval.decided_by = "Sales Manager"
    approval.decision_note = "Approved in demo flow." if approved else "Rejected in demo flow."
    approval.decided_at = datetime.now(UTC)

    quote = approval.quote_draft
    inquiry = quote.inquiry
    quote.status = "approved" if approved else "rejected"
    inquiry.status = "approved" if approved else "rejected"

    write_audit_event(
        db,
        entity_type="approval_request",
        entity_id=approval.id,
        event_type="approval_approved" if approved else "approval_rejected",
        actor="approver",
        message=f"Approval request {approval.id} {'approved' if approved else 'rejected'}.",
        payload={
            "approval_request_id": approval.id,
            "quote_draft_id": quote.id,
            "inquiry_id": inquiry.id,
            "status": approval.status,
        },
    )
    db.commit()
    return approval


@router.post("/approvals/{approval_id}/approve", response_model=ApprovalRequestSchema)
def approve_quote(approval_id: int, db: Session = Depends(get_db)):
    return _decide_approval(db, approval_id, True)


@router.post("/approvals/{approval_id}/reject", response_model=ApprovalRequestSchema)
def reject_quote(approval_id: int, db: Session = Depends(get_db)):
    return _decide_approval(db, approval_id, False)


@router.get("/audit", response_model=list[AuditEventSchema])
def list_audit(db: Session = Depends(get_db)):
    return db.scalars(select(AuditEvent).order_by(desc(AuditEvent.created_at))).all()
