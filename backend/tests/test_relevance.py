from __future__ import annotations

import pytest
from PIL import Image

from fileora.domain import Extraction, Unit
from fileora.retrieval import Filters, SearchRequest


def test_bcnf_keyword_does_not_fill_unrelated_modality_tabs(service, corpus, monkeypatch):
    (corpus / "dbms.pdf").write_bytes(b"fixture PDF")
    (corpus / "sorting.py").write_text("def sort(values):\n    return sorted(values)\n")
    Image.new("RGB", (32, 32), "white").save(corpus / "holiday.png")
    Image.new("RGB", (32, 32), "black").save(corpus / "diagram.png")
    original = service.indexer.extractor

    def fixture_extract(path, settings):
        if path.name == "dbms.pdf":
            return Extraction(
                [Unit("BCNF database normalization", locator={"page": 14})], modality="document"
            )
        if path.name == "diagram.png":
            return Extraction([Unit("BCNF decomposition", kind="ocr")], modality="image")
        return original(path, settings)

    service.indexer.extractor = fixture_extract
    assert not service.indexer.run(service.indexer.create_job())["failed"]
    service.settings.enable_vision = True
    # Even a very high vector score cannot manufacture a literal keyword match.
    monkeypatch.setattr(
        service.indexes,
        "search",
        lambda *args: [(r["id"], 0.95) for r in service.search._eligible(Filters())],
    )
    for query in ("BCNF", "bcnf", "Find my notes about BCNF"):
        all_results = service.search.run(SearchRequest(query=query))["results"]
        assert {r["name"] for r in all_results} == {"dbms.pdf", "diagram.png"}
        for modality, expected in (
            ("document", {"dbms.pdf"}),
            ("code", set()),
            ("image", {"diagram.png"}),
        ):
            results = service.search.run(
                SearchRequest(query=query, filters=Filters(modality=modality))
            )["results"]
            assert {r["name"] for r in results} == expected
            assert all(r["match_kind"] == "terms" for r in results)


@pytest.mark.parametrize("mode", ["hybrid", "semantic"])
def test_weak_neighbors_are_removed_before_fusion_and_reranking(service, corpus, monkeypatch, mode):
    service.settings.enable_vision = True
    monkeypatch.setattr(
        service.models, "encode_vision", lambda *args, **kwargs: [None], raising=False
    )
    ids = [r["id"] for r in service.search._eligible(Filters())]
    monkeypatch.setattr(service.indexes, "search", lambda *args: [(i, 0.1) for i in ids])

    def unexpected_rerank(*args):
        pytest.fail("Rejected weak candidates must not be reintroduced by reranking")

    monkeypatch.setattr(service.models, "rerank", unexpected_rerank, raising=False)
    for filters in (Filters(), Filters(modality="text"), Filters(extension=".txt")):
        output = service.search.run(
            SearchRequest(query="medieval French poetry", mode=mode, filters=filters, rerank=True)
        )
        assert output["results"] == []


def test_strong_paraphrase_remains_searchable_without_literal_words(service, corpus, monkeypatch):
    row = next(r for r in service.search._eligible(Filters()) if r["name"] == "semaphores.md")
    monkeypatch.setattr(service.indexes, "search", lambda *args: [(row["id"], 0.7)])
    output = service.search.run(SearchRequest(query="coordinate simultaneous execution safely"))
    assert output["results"][0]["name"] == "semaphores.md"
    assert output["results"][0]["match_kind"] == "semantic"


def test_incidental_shared_word_in_sentence_is_not_a_hybrid_match(service, corpus, monkeypatch):
    monkeypatch.setattr(service.indexes, "search", lambda *args: [])
    assert not service.search.run(SearchRequest(query="priority birthday invitation"))["results"]
    # Literal OR-term retrieval remains available when explicitly selected.
    assert service.search.run(SearchRequest(query="priority birthday invitation", mode="lexical"))[
        "results"
    ]


def test_visual_paraphrase_uses_its_own_cosine_floor(service, corpus, monkeypatch):
    Image.new("RGB", (32, 32), "white").save(corpus / "holiday.png")
    service.indexer.run(service.indexer.create_job())
    row = next(r for r in service.search._eligible(Filters()) if r["name"] == "holiday.png")
    service.settings.enable_vision = True
    monkeypatch.setattr(
        service.models, "encode_vision", lambda *args, **kwargs: [None], raising=False
    )
    monkeypatch.setattr(service.indexes, "search", lambda *args: [(row["id"], 0.4)])
    output = service.search.run(
        SearchRequest(query="a sandy tropical beach", mode="semantic", channels="vision")
    )
    assert output["results"][0]["match_kind"] == "visual"
    monkeypatch.setattr(service.indexes, "search", lambda *args: [(row["id"], 0.1)])
    assert not service.search.run(
        SearchRequest(query="a sandy tropical beach", mode="semantic", channels="vision")
    )["results"]
