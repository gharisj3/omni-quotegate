from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.models import Customer
from app.routes.api import router as api_router
from app.routes.pages import router as pages_router
from app.seed import reset_and_seed


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        has_customers = db.scalar(select(Customer.id).limit(1))
        if has_customers is None:
            reset_and_seed(db)
    yield


app = FastAPI(title="Omni QuoteGate", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(pages_router)
app.include_router(api_router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "omni-quotegate"}
