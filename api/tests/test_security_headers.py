"""
Tests for Institutional Security Headers (Issue #41).
Verifies that all API responses include defense-in-depth headers:
- X-Content-Type-Options: nosniff
- X-Frame-Options: DENY
- Strict-Transport-Security: max-age=31536000; includeSubDomains
- Content-Security-Policy: strict default-src 'none' for JSON API, scoped for /demo
"""

def test_api_responses_include_mandatory_security_headers(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert "max-age=31536000" in resp.headers["strict-transport-security"]
    assert "default-src 'none'" in resp.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in resp.headers["content-security-policy"]


def test_demo_route_has_scoped_content_security_policy(client):
    resp = client.get("/demo")
    assert resp.status_code == 200
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert "max-age=31536000" in resp.headers["strict-transport-security"]
    csp = resp.headers["content-security-policy"]
    assert "default-src 'self'" in csp
    assert "'unsafe-inline'" in csp
    assert "frame-ancestors 'none'" in csp


def test_error_responses_still_contain_security_headers(client):
    # 404 Not Found
    resp = client.get("/nonexistent-endpoint-404")
    assert resp.status_code == 404
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert "max-age=31536000" in resp.headers["strict-transport-security"]
    assert "default-src 'none'" in resp.headers["content-security-policy"]


def test_cors_preflight_for_allowed_origin(client):
    """CORS preflight from an authorized frontend origin succeeds."""
    headers = {
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type",
    }
    resp = client.options("/auth/login", headers=headers)
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert resp.headers.get("access-control-allow-credentials") == "true"


def test_cors_rejects_unauthorized_origin(client):
    """CORS preflight from an unauthorized origin is not granted allow-origin."""
    headers = {
        "Origin": "http://malicious-external-site.com",
        "Access-Control-Request-Method": "GET",
    }
    resp = client.options("/health", headers=headers)
    assert "access-control-allow-origin" not in resp.headers


def test_cors_wildcard_strictly_prohibited():
    """Wildcard origin '*' is blocked with an explicit security error."""
    import pytest
    from app.config import Settings

    s = Settings(CORS_ORIGINS="http://localhost:5173,*")
    with pytest.raises(ValueError, match="Wildcard origin.*strictly forbidden"):
        _ = s.cors_origins_list

