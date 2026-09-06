"""
FastAPI entrypoint. Run locally with: uvicorn app.main:app --reload
Or via Docker Compose: docker compose up api

Every router below corresponds 1:1 to a resource group in SYSTEM_DESIGN.md's
Interface Contracts endpoint table — add a new endpoint by adding a route to
the matching router, not by creating a new top-level file per feature.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import (
    auth, orgs, cases, evidence_requests, documents, bail, trial, audit, admin, reports, demo,
)

app = FastAPI(
    title="SIH26190 — Secure Digital Document Management System",
    description="See SYSTEM_DESIGN.md at the repo root for the full architecture.",
    version="0.1.0",
)

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """
    Institutional security headers middleware (Issue #41).
    Enforces defense-in-depth on all API responses:
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - Strict-Transport-Security: max-age=31536000; includeSubDomains
    - Content-Security-Policy: strict for JSON API, scoped for demo/docs
    """
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    path = request.url.path
    if path.startswith("/demo"):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; frame-ancestors 'none';"
        )
    elif path.startswith(("/docs", "/redoc", "/openapi.json")):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self' https://cdn.jsdelivr.net; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https://fastapi.tiangolo.com; "
            "frame-ancestors 'none';"
        )
    else:
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none';"

    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
