from __future__ import annotations


def test_search_contract(client):
    response = client.post("/api/v1/search", json={"query": "Dijkstra", "mode": "lexical"})
    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["relative_path"] == "graphs.txt"
    assert result["evidence"][0]["locator"]["line_start"] == 1
    assert (
        client.get(f"/api/v1/files/{result['file_id']}/preview")
        .headers["content-type"]
        .startswith("text/plain")
    )


def test_api_docs_are_local_under_csp(client):
    html = client.get("/api/docs")
    assert html.status_code == 200
    assert "cdn" not in html.text
    assert "/api/docs-assets/swagger-ui-bundle.js" in html.text
    assert "validatorUrl: null" in client.get("/api/docs-init.js").text
    assert client.get("/api/openapi.json").json()["info"]["title"] == "Fileora local API"


def test_security(client):
    for headers in (
        {"origin": "https://evil.example"},
        {"host": "evil.example"},
        {"sec-fetch-site": "cross-site"},
    ):
        assert client.get("/api/v1/health", headers=headers).status_code == 403
    assert (
        client.post(
            "/api/v1/search", json={"query": "Dijkstra"}, headers={"x-fileora-token": "wrong"}
        ).status_code
        == 403
    )
    response = client.get("/api/v1/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_invalid_input_and_missing_paths(client):
    assert client.post("/api/v1/search", json={"query": " "}).status_code == 422
    assert client.post("/api/v1/search", json={"query": "x", "limit": 100}).status_code == 422
    assert client.get("/api/v1/files/99999").status_code == 404
    assert client.get("/api/v1/files/99999/preview").status_code == 404
    assert client.get("/api/v1/assets/99999").status_code == 404
    assert client.get("/api/v1/does-not-exist").status_code == 404


def test_job_routes(client):
    result = client.post("/api/v1/index/jobs", json={"verify": True})
    assert result.status_code == 202
    job_id = result.json()["job_id"]
    assert client.get(f"/api/v1/jobs/{job_id}").status_code == 200
    assert client.post(f"/api/v1/jobs/{job_id}/cancel").status_code == 202


def test_final_v4_exposes_search_without_v5_generation(client):
    assert client.post("/api/v1/answer", json={"query": "Dijkstra"}).status_code in (404, 405)
    assert "/api/v1/answer" not in client.get("/api/openapi.json").json()["paths"]
    assert (
        client.post("/api/v1/search", json={"query": "Dijkstra", "mode": "lexical"}).status_code
        == 200
    )
