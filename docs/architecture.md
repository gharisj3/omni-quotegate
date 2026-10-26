# Omni QuoteGate Architecture

## System Overview

Omni QuoteGate is a FastAPI application that demonstrates controlled ERP sales automation. It receives seeded customer inquiries, looks up mocked ERP data, drafts quotes, routes flagged quotes to separate demo review routes, and records workflow events. Reviewer identity is not authenticated.

## Module Overview

- Inquiry Inbox: lists inbound customer requests and their workflow state.
- ERP Lookup Panel: shows matched product and customer credit context from the mock adapter.
- Rules-Based Quote Draft: deterministic engine that classifies, looks up, and proposes quote drafts.
- Approval Queue + Audit Timeline: demo review surface plus application-written event records.

## Draft Workflow and Demo Review Routes

```mermaid
flowchart LR
    subgraph Draft["Deterministic draft functions"]
        A["classify_inquiry()"]
        B["lookup_product()"]
        C["lookup_customer()"]
        D["propose_quote()"]
    end

    subgraph DB["State and audit boundary"]
        E["SQLite database"]
        F["Audit event records"]
    end

    subgraph Reviewer["Separate demo review routes"]
        G["Approve quote"]
        H["Reject quote"]
        I["Quote review status"]
    end

    A --> E
    B --> E
    C --> E
    D --> E
    D --> F
    G --> E
    G --> F
    H --> E
    H --> F
    I --> E
```

The rules engine reads seeded context and drafts a recommendation. Separate routes record quote review decisions. No LLM is called and no authenticated human-only boundary is enforced; a production deployment must add identity and authorization.

## Mock ERP Adapter

`app/services/mock_erp.py` exposes product search, customer context lookup, and stock checks behind a clean adapter class. In v1 it reads local database records, but the same contract can be replaced later with Odoo XML-RPC, Oracle/Fusion, SAP, or a custom ERP API adapter.

## Audit Trail Design

Normal workflow operations insert audit events, but the demo reset route can delete records. These events are not tamper-proof. Each meaningful state change writes a human-readable event with JSON payload context so the demo can show how decisions are tracked over time.

## Future Odoo XML-RPC Adapter Plan

The ERP adapter boundary is intentionally narrow: search products, fetch customer context, and check stock. That makes Odoo XML-RPC replacement straightforward without rewriting the approval or audit workflow.

## Reset Demo Note

`POST /admin/reset-demo` exists as a demo-only convenience so the seeded workflow can be restored quickly during portfolio walkthroughs. It is intentionally open in v1 and is not production-safe.
