from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fileora.api import create_app


@pytest.fixture
def client(service, corpus):
    with TestClient(create_app(service=service), base_url="http://127.0.0.1:8765") as client:
        client.headers["x-fileora-token"] = client.get("/api/v1/session").json()["token"]
        yield client


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


def test_unknown_ollama_error_is_actionable(client, monkeypatch):
    import httpx

    import fileora.assistant

    def unavailable(*args, **kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(fileora.assistant.httpx, "post", unavailable)
    result = client.post("/api/v1/answer", json={"query": "Dijkstra", "mode": "lexical"})
    assert result.status_code == 503
    assert result.json()["error"]["code"] == "LLM_UNAVAILABLE"
    assert (
        client.post("/api/v1/search", json={"query": "Dijkstra", "mode": "lexical"}).status_code
        == 200
    )


@pytest.mark.parametrize(
    "content,code",
    [("A claim [E999]", "INVALID_CITATIONS"), ("A claim without citation", "INVALID_CITATIONS")],
)
def test_unknown_citations_rejected(client, monkeypatch, content, code):
    import httpx

    import fileora.assistant

    monkeypatch.setattr(
        fileora.assistant.httpx,
        "post",
        lambda *args, **kwargs: httpx.Response(
            200,
            json={"message": {"content": content}},
            request=httpx.Request("POST", "http://127.0.0.1"),
        ),
    )
    result = client.post("/api/v1/answer", json={"query": "Dijkstra", "mode": "lexical"})
    assert result.status_code == 422
    assert result.json()["error"]["code"] == code


def test_valid_citation_and_refusal(client, monkeypatch):
    import httpx

    import fileora.assistant

    monkeypatch.setattr(
        fileora.assistant.httpx,
        "post",
        lambda *args, **kwargs: httpx.Response(
            200,
            json={"message": {"content": "Dijkstra uses a priority queue [E1]."}},
            request=httpx.Request("POST", "http://127.0.0.1"),
        ),
    )
    result = client.post("/api/v1/answer", json={"query": "Dijkstra", "mode": "lexical"}).json()
    assert result["citations"][0]["id"] == "E1"
    assert result["supported"] is None
    monkeypatch.setattr(
        fileora.assistant.httpx,
        "post",
        lambda *args, **kwargs: httpx.Response(
            200,
            json={"message": {"content": "INSUFFICIENT_EVIDENCE"}},
            request=httpx.Request("POST", "http://127.0.0.1"),
        ),
    )
    assert (
        client.post("/api/v1/answer", json={"query": "Dijkstra", "mode": "lexical"}).json()[
            "supported"
        ]
        is False
    )
