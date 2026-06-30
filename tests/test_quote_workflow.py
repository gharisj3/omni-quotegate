from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import ApprovalRequest, AuditEvent, Inquiry
from app.seed import reset_and_seed


SQLALCHEMY_DATABASE_URL = "sqlite:///./test_omni_quotegate.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}, future=True)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestingSessionLocal() as db:
        reset_and_seed(db)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    engine.dispose()
    if Path("test_omni_quotegate.db").exists():
        Path("test_omni_quotegate.db").unlink()


def test_quote_drafting_creates_quote(client: TestClient):
    response = client.post("/api/v1/inquiries/1/draft-quote")
    assert response.status_code == 200
    data = response.json()
    assert data["quote_draft"] is not None
    assert data["quote_draft"]["status"] == "pending_approval"


def test_approval_required_when_quantity_exceeds_stock(client: TestClient):
    response = client.post("/api/v1/inquiries/1/draft-quote")
    assert response.status_code == 200
    assert response.json()["quote_draft"]["approval_required"] is True


def test_approval_required_when_discount_exceeds_standard(client: TestClient):
    response = client.post("/api/v1/inquiries/4/draft-quote")
    assert response.status_code == 200
    assert "DISCOUNT_ABOVE_STANDARD" in response.json()["quote_draft"]["risk_summary"]


def test_approval_required_when_customer_near_credit_limit(client: TestClient):
    response = client.post("/api/v1/inquiries/3/draft-quote")
    assert response.status_code == 200
    assert "CUSTOMER_NEAR_CREDIT_LIMIT" in response.json()["quote_draft"]["risk_summary"]


def test_approval_required_when_customer_over_credit_limit(client: TestClient):
    response = client.post("/api/v1/inquiries/5/draft-quote")
    assert response.status_code == 200
    assert "CUSTOMER_OVER_CREDIT_LIMIT" in response.json()["quote_draft"]["risk_summary"]


def test_approving_updates_quote_and_inquiry_status(client: TestClient):
    client.post("/api/v1/inquiries/1/draft-quote")
    approvals = client.get("/api/v1/approvals").json()
    approval_id = approvals[0]["id"]
    response = client.post(f"/api/v1/approvals/{approval_id}/approve")
    assert response.status_code == 200
    with TestingSessionLocal() as db:
        inquiry = db.get(Inquiry, 1)
        approval = db.get(ApprovalRequest, approval_id)
        assert inquiry.status == "approved"
        assert approval.status == "approved"


def test_audit_events_created_during_quote_workflow(client: TestClient):
    client.post("/api/v1/inquiries/1/draft-quote")
    with TestingSessionLocal() as db:
        events = db.scalars(select(AuditEvent).order_by(AuditEvent.id)).all()
        event_types = {event.event_type for event in events}
        assert "inquiry_created" in event_types
        assert "quote_drafted" in event_types
        assert "approval_requested" in event_types
