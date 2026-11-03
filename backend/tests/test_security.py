"""Tests for A2 security features: rate limiting, security headers, CSRF logging."""

import pytest


@pytest.mark.asyncio
async def test_security_headers_present(client):
    """Every response should carry the required security headers."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"
    assert response.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    assert "camera=()" in (response.headers.get("permissions-policy") or "")


@pytest.mark.asyncio
async def test_api_response_no_store(client):
    """API responses must carry Cache-Control: no-store."""
    response = await client.get("/api/v1/auth/me")
    assert response.headers.get("cache-control") == "no-store"


@pytest.mark.asyncio
async def test_register_rate_limit(client):
    """Rate-limiting kicks in after the configured threshold."""
    payload = {
        "full_name": "Rate Test",
        "email": "rate@example.com",
        "password": "ValidPassword123!",
        "confirm_password": "ValidPassword123!",
        "terms_accepted": True,
    }
    # Fire requests up to the limit (10 per 900s)
    responses = [await client.post("/api/v1/auth/register", json=payload) for _ in range(11)]
    status_codes = [r.status_code for r in responses]
    assert 429 in status_codes


@pytest.mark.asyncio
async def test_login_rate_limit(client):
    """Login rate limit applies per IP."""
    payload = {"email": "nobody@example.com", "password": "wrongpassword"}
    responses = [await client.post("/api/v1/auth/login", json=payload) for _ in range(21)]
    status_codes = [r.status_code for r in responses]
    assert 429 in status_codes
