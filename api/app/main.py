"""
FastAPI entrypoint. Run locally with: uvicorn app.main:app --reload
Or via Docker Compose: docker compose up api

Every router below corresponds 1:1 to a resource group in SYSTEM_DESIGN.md's
Interface Contracts endpoint table — add a new endpoint by adding a route to
the matching router, not by creating a new top-level file per feature.
"""

from fastapi import FastAPI

from app.routers import (
    auth, orgs, cases, evidence_requests, documents, bail, trial, audit, admin, reports, demo,
)

app = FastAPI(
    title="SIH26190 — Secure Digital Document Management System",
    description="See SYSTEM_DESIGN.md at the repo root for the full architecture.",
    version="0.1.0",
)

app.include_router(auth.router)
app.include_router(orgs.router)
app.include_router(cases.router)
app.include_router(evidence_requests.router)
app.include_router(documents.router)
app.include_router(bail.router)
app.include_router(trial.router)
app.include_router(audit.router)
app.include_router(admin.router)
app.include_router(reports.router)
app.include_router(demo.router)


@app.get("/health")
def health():
    """Not part of the design's endpoint table — an ops convenience only."""
    return {"status": "ok"}
