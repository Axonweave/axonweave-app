from httpx import AsyncClient


async def test_health_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body


async def test_health_includes_correlation_id_header(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert "x-correlation-id" in response.headers


async def test_health_correlation_id_echoed(client: AsyncClient) -> None:
    cid = "test-correlation-id-12345"
    response = await client.get("/health", headers={"X-Correlation-ID": cid})
    assert response.headers.get("x-correlation-id") == cid
