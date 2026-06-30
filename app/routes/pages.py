from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, joinedload

from app.config import format_currency
from app.database import get_db
from app.models import ApprovalRequest, AuditEvent, Inquiry, QuoteDraft, QuoteLineDraft
from app.routes.api import _decide_approval
from app.seed import reset_and_seed
from app.services.ai_quote_engine import AIQuoteEngine, analyze_inquiry

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="app/templates")
templates.env.globals["format_currency"] = format_currency


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    total_inquiries = db.scalar(select(func.count()).select_from(Inquiry)) or 0
    pending_approvals = db.scalar(
        select(func.count()).select_from(ApprovalRequest).where(ApprovalRequest.status == "pending")
    ) or 0
    approved_quotes = db.scalar(
        select(func.count()).select_from(QuoteDraft).where(QuoteDraft.status == "approved")
    ) or 0
    estimated_value = db.scalar(select(func.coalesce(func.sum(QuoteDraft.total_amount), 0)).select_from(QuoteDraft)) or 0
    recent_events = db.scalars(select(AuditEvent).order_by(desc(AuditEvent.created_at)).limit(8)).all()
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "total_inquiries": total_inquiries,
            "pending_approvals": pending_approvals,
            "approved_quotes": approved_quotes,
            "estimated_value": estimated_value,
            "recent_events": recent_events,
        },
    )


@router.get("/inquiries")
def inquiries(request: Request, db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Inquiry).order_by(desc(Inquiry.created_at)).options(joinedload(Inquiry.customer))
    ).all()
    return templates.TemplateResponse("inquiries.html", {"request": request, "inquiries": rows})


@router.get("/inquiries/{inquiry_id}")
def inquiry_detail(inquiry_id: int, request: Request, db: Session = Depends(get_db)):
    inquiry = db.scalars(
        select(Inquiry)
        .where(Inquiry.id == inquiry_id)
        .options(
            joinedload(Inquiry.customer),
            joinedload(Inquiry.quote_draft).joinedload(QuoteDraft.lines).joinedload(QuoteLineDraft.product),
        )
    ).first()
    if inquiry is None:
        return RedirectResponse("/", status_code=303)

    approval = inquiry.quote_draft.approval_request if inquiry.quote_draft else None
    audit_events = db.scalars(
        select(AuditEvent)
        .where(
            ((AuditEvent.entity_type == "inquiry") & (AuditEvent.entity_id == inquiry.id))
            | (
                (AuditEvent.entity_type == "quote_draft")
                & (AuditEvent.entity_id == (inquiry.quote_draft.id if inquiry.quote_draft else -1))
            )
        )
        .order_by(desc(AuditEvent.created_at))
    ).all()
    return templates.TemplateResponse(
        "inquiry_detail.html",
        {"request": request, "inquiry": inquiry, "approval": approval, "audit_events": audit_events},
    )


@router.post("/inquiries/{inquiry_id}/analyze")
def analyze_inquiry_page(inquiry_id: int, db: Session = Depends(get_db)):
    analyze_inquiry(db, inquiry_id)
    db.commit()
    return RedirectResponse(f"/inquiries/{inquiry_id}", status_code=303)


@router.post("/inquiries/{inquiry_id}/draft-quote")
def draft_quote_page(inquiry_id: int, db: Session = Depends(get_db)):
    inquiry = db.get(Inquiry, inquiry_id)
    if inquiry:
        AIQuoteEngine(db).propose_quote(inquiry)
        db.commit()
    return RedirectResponse(f"/inquiries/{inquiry_id}", status_code=303)


@router.get("/approvals")
def approvals(request: Request, db: Session = Depends(get_db)):
    rows = db.scalars(
        select(ApprovalRequest)
        .order_by(desc(ApprovalRequest.created_at))
        .options(
            joinedload(ApprovalRequest.quote_draft).joinedload(QuoteDraft.customer),
            joinedload(ApprovalRequest.quote_draft).joinedload(QuoteDraft.inquiry),
        )
    ).all()
    return templates.TemplateResponse("approvals.html", {"request": request, "approvals": rows})


@router.post("/approvals/{approval_id}/approve")
def approve_page(approval_id: int, db: Session = Depends(get_db)):
    _decide_approval(db, approval_id, True)
    return RedirectResponse("/approvals", status_code=303)


@router.post("/approvals/{approval_id}/reject")
def reject_page(approval_id: int, note: str = Form(default=""), db: Session = Depends(get_db)):
    approval = _decide_approval(db, approval_id, False)
    if note:
        approval.decision_note = note
        db.commit()
    return RedirectResponse("/approvals", status_code=303)


@router.get("/audit")
def audit(request: Request, db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditEvent).order_by(desc(AuditEvent.created_at))).all()
    return templates.TemplateResponse("audit.html", {"request": request, "events": rows})


@router.post("/admin/reset-demo")
def reset_demo(db: Session = Depends(get_db)):
    reset_and_seed(db)
    return RedirectResponse("/", status_code=303)
