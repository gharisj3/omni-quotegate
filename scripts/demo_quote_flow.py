"""Run the quote reject, redraft, approve sequence against temporary SQLite data."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="quotegate-demo-") as folder:
        database_path = (Path(folder) / "demo.db").as_posix()
        os.environ["DATABASE_URL"] = f"sqlite:///{database_path}"
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

        from fastapi.testclient import TestClient

        from app.database import engine
        from app.main import app

        with TestClient(app) as client:
            draft = client.post("/api/v1/inquiries/1/draft-quote")
            draft.raise_for_status()
            approval_id = client.get("/api/v1/approvals").json()[0]["id"]

            reason = "Requested quantity exceeds available stock."
            rejected = client.post(
                f"/api/v1/approvals/{approval_id}/reject", params={"reason": reason}
            )
            rejected.raise_for_status()

            redraft = client.post("/api/v1/inquiries/1/draft-quote")
            redraft.raise_for_status()
            pending = next(
                item
                for item in client.get("/api/v1/approvals").json()
                if item["status"] == "pending"
            )
            approved = client.post(f"/api/v1/approvals/{pending['id']}/approve")
            approved.raise_for_status()

            events = client.get("/api/v1/audit").json()
            print(
                "Fixture mode: seeded local ERP records; no API or external service call."
            )
            print(
                json.dumps(
                    {
                        "steps": [
                            "draft quote",
                            {"reject": reason},
                            "redraft quote",
                            "approve quote",
                        ],
                        "decision_note": approved.json()["decision_note"],
                        "audit_events": [
                            event["event_type"]
                            for event in reversed(events)
                            if event["event_type"]
                            in {
                                "quote_drafted",
                                "approval_requested",
                                "approval_rejected",
                                "approval_approved",
                            }
                        ],
                    },
                    indent=2,
                )
            )
        engine.dispose()


if __name__ == "__main__":
    main()
