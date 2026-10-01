from __future__ import annotations

import json
import math
import re
import time
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from fileora.chunking import offsets
from fileora.domain import FileoraError

STOP_WORDS = {
    "find",
    "my",
    "the",
    "a",
    "an",
    "about",
    "where",
    "is",
    "are",
    "i",
    "me",
    "of",
    "in",
    "on",
    "to",
    "and",
    "with",
    "notes",
    "documents",
    "file",
    "files",
    "for",
    "did",
    "how",
    "can",
    "what",
    "was",
    "it",
    "at",
    "this",
    "that",
    "please",
    "show",
    "which",
    "when",
}


def query_terms(query: str) -> list[str]:
    original = re.findall(r"[^\W_]+", query, re.UNICODE)
    split = re.findall(r"[^\W_]+", re.sub(r"([a-z])([A-Z])", r"\1 \2", query), re.UNICODE)
    tokens = list(dict.fromkeys(t.lower() for t in original + split))
    return [t for t in tokens if t not in STOP_WORDS]


def strong_candidates(branch: list[tuple[int, float]], minimum: float) -> list[tuple[int, float]]:
    # Apply absolute cosine floors before RRF. Rank scores cannot distinguish a
    # weak first neighbor from a genuinely related result, especially after filters.
    return [(i, s) for i, s in branch if math.isfinite(s) and s >= minimum]


class Filters(BaseModel):
    root_id: int | None = None
    modality: Literal["text", "document", "code", "image", "audio", "video"] | None = None
    extension: str | None = None
    path_prefix: str | None = Field(default=None, max_length=512)
    modified_after: datetime | None = None
    modified_before: datetime | None = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=10, ge=1, le=50)
    mode: Literal["semantic", "lexical", "hybrid"] = "hybrid"
    filters: Filters = Field(default_factory=Filters)
    rerank: bool = False
    channels: Literal["all", "text", "vision"] = "all"

    @field_validator("query")
    @classmethod
    def nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Enter a nonempty query")
        return value.strip()


def rrf(
    branches: list[list[tuple[int, float]]], weights: list[float] | None = None
) -> list[tuple[int, float]]:
    scores: dict[int, float] = {}
    for branch_index, branch in enumerate(branches):
        weight = weights[branch_index] if weights is not None else 1.0
        seen = set()
        for rank, (item, _) in enumerate(branch, 1):
            if item not in seen:
                scores[item] = scores.get(item, 0) + weight / (60 + rank)
                seen.add(item)
    return sorted(scores.items(), key=lambda x: (-x[1], x[0]))


def evidence(row: dict) -> dict:
    return {
        "chunk_id": row["id"],
        "kind": row["kind"],
        "snippet": row["text"][:1400],
        "locator": json.loads(row["locator"]),
        "symbol": row["symbol"],
        "asset_url": f"/api/v1/assets/{row['id']}" if row["asset"] else None,
    }


class Search:
    def __init__(self, store, settings, models, indexes, lock):
        self.store, self.settings, self.models, self.indexes, self.lock = (
            store,
            settings,
            models,
            indexes,
            lock,
        )

    def _eligible(self, filters: Filters, full: bool = True) -> list[dict]:
        columns = (
            """c.*,f.id AS file_id,f.name,f.path,f.relative_path,f.extension,f.modality,
        f.mtime_ns,f.size,f.root_id,v.sha256,v.warnings FROM chunks c
        """
            if full
            else "c.id,f.id AS file_id FROM chunks c "
        )
        sql = (
            "SELECT "
            + columns
            + """
        JOIN files f ON f.active_revision_id=c.revision_id JOIN file_revisions v ON v.id=c.revision_id
        JOIN roots r ON r.id=f.root_id WHERE f.status='ready' AND r.enabled=1 AND r.status='ready'"""
        )
        args = []
        for column, value in (
            ("f.root_id", filters.root_id),
            ("f.modality", filters.modality),
            ("f.extension", filters.extension.lower() if filters.extension else None),
        ):
            if value is not None:
                sql += f" AND {column}=?"
                args.append(value)
        if filters.path_prefix:
            sql += " AND f.relative_path LIKE ? ESCAPE '\\'"
            args.append(
                filters.path_prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                + "%"
            )
        for comparison, date_value in (
            (">=", filters.modified_after),
            ("<=", filters.modified_before),
        ):
            if date_value:
                sql += f" AND f.mtime_ns{comparison}?"
                args.append(int(date_value.timestamp() * 1e9))
        return self.store.rows(sql, tuple(args))

    def _hydrate(self, ids: set[int]) -> dict[int, dict]:
        if not ids:
            return {}
        rows = self.store.rows(
            f"""SELECT c.*,f.id AS file_id,f.name,f.path,f.relative_path,f.extension,f.modality,
            f.mtime_ns,f.size,f.root_id,v.sha256,v.warnings FROM chunks c
            JOIN files f ON f.active_revision_id=c.revision_id JOIN file_revisions v ON v.id=c.revision_id
            WHERE c.id IN ({",".join("?" for _ in ids)}) AND f.status='ready'""",
            tuple(ids),
        )
        return {row["id"]: row for row in rows}

    def lexical(self, query: str, allowed: set[int], count: int) -> list[tuple[int, float]]:
        terms = query_terms(query)
        if not terms:
            return []
        match = " OR ".join('"' + t.replace('"', '""') + '"' for t in terms)
        # Filter before LIMIT; a global top-K followed by filtering is incorrect.
        with self.store.connect() as db:
            db.execute("CREATE TEMP TABLE eligible(id INTEGER PRIMARY KEY)")
            db.executemany("INSERT INTO eligible VALUES(?)", [(i,) for i in allowed])
            rows = db.execute(
                """SELECT chunks_fts.rowid AS id,bm25(chunks_fts,1,3,1,4) AS score
          FROM chunks_fts JOIN chunks c ON c.id=chunks_fts.rowid
          JOIN files f ON f.active_revision_id=c.revision_id JOIN roots r ON r.id=f.root_id
          JOIN eligible ON eligible.id=c.id
          WHERE chunks_fts MATCH ? AND f.status='ready' AND r.status='ready' AND r.enabled=1
          ORDER BY score,chunks_fts.rowid LIMIT ?""",
                (match, count),
            ).fetchall()
        return [(r["id"], float(r["score"])) for r in rows]

    def run(self, request: SearchRequest) -> dict:
        started = time.perf_counter()
        warnings = []
        reranked = False
        keyword_only = (
            request.mode == "hybrid"
            and request.channels != "vision"
            and len(query_terms(request.query)) == 1
        )
        tokenizer = (
            self.models.tokenizer()
            if self.models.available(self.settings.text_model)
            and request.mode != "lexical"
            and request.channels != "vision"
            and not keyword_only
            else None
        )
        if len(offsets(request.query, tokenizer)) > 128:
            raise FileoraError("QUERY_TOO_LONG", "Queries may contain at most 128 model tokens")
        with self.lock:
            eligible = self._eligible(request.filters, full=False)
            allowed = {r["id"] for r in eligible}
            allowed_files = {r["file_id"] for r in eligible}
            count = max(50, request.limit * 5)
            text_branches = []
            if request.channels == "vision" and (
                not self.settings.enable_vision or request.mode == "lexical"
            ):
                raise FileoraError(
                    "VISION_DISABLED",
                    "Visual-only retrieval requires --vision and semantic or hybrid mode",
                )
            if request.mode != "semantic" and request.channels != "vision":
                lexical = self.lexical(request.query, allowed, count)
                terms = set(query_terms(request.query))
                if request.mode == "hybrid" and len(terms) > 1:
                    rows = self._hydrate({i for i, _ in lexical})
                    # A lone shared word in a longer query (e.g. "map" in
                    # "map of the moon") is insufficient lexical evidence.
                    lexical = [
                        (i, s)
                        for i, s in lexical
                        if len(
                            terms
                            & set(
                                query_terms(
                                    " ".join(
                                        rows[i][key] or ""
                                        for key in ("text", "name", "relative_path", "symbol")
                                    )
                                )
                            )
                        )
                        >= 2
                    ]
                text_branches.append(lexical)
            if request.mode != "lexical" and request.channels != "vision" and not keyword_only:
                try:
                    profile = self.models.profile()
                    query = self.models.encode_text([request.query], query=True)[0]
                    filtered = allowed if request.filters.model_dump(exclude_none=True) else None
                    semantic = self.indexes.search(profile, query, filtered, count)
                    text_branches.append(
                        strong_candidates(
                            [(i, s) for i, s in semantic if i in allowed],
                            self.settings.text_similarity_floor,
                        )
                    )
                    if not self.store.one(
                        "SELECT id FROM embeddings WHERE profile_id=? LIMIT 1", (profile["id"],)
                    ):
                        warnings.append("No text embeddings exist for this model. Run a rescan.")
                except FileoraError as exc:
                    if request.mode == "semantic":
                        raise
                    warnings.append(exc.message + "; returning lexical matches")
            text_ranking = (
                rrf(text_branches)
                if request.mode == "hybrid"
                else (text_branches[0] if text_branches else [])
            )
            by_id = self._hydrate({i for i, _ in text_ranking})
            if (
                request.rerank
                and text_ranking
                and any(by_id[i]["text"].strip() for i, _ in text_ranking)
            ):
                head = [(i, s) for i, s in text_ranking[:20] if by_id[i]["text"].strip()]
                scores = self.models.rerank(request.query, [by_id[i]["text"] for i, _ in head])
                reordered = sorted(
                    zip([i for i, _ in head], scores, strict=True), key=lambda x: (-x[1], x[0])
                )
                done = {i for i, _ in reordered}
                text_ranking = reordered + [(i, s) for i, s in text_ranking if i not in done]
                reranked = True
            visual_ranking = []
            if (
                self.settings.enable_vision
                and request.mode != "lexical"
                and request.channels != "text"
                and not keyword_only
            ):
                try:
                    profile = self.models.profile("vision")
                    query = self.models.encode_vision([request.query], query=True)[0]
                    visual_ranking = strong_candidates(
                        self.indexes.search(profile, query, allowed, count),
                        self.settings.min_vision_similarity,
                    )
                    by_id.update(self._hydrate({i for i, _ in visual_ranking}))
                except FileoraError as exc:
                    if request.channels == "vision":
                        raise
                    warnings.append(exc.message)

            def files_for(branch):
                seen, output = set(), []
                for unit_id, score in branch:
                    row = by_id.get(unit_id)
                    if row and row["file_id"] not in seen:
                        seen.add(row["file_id"])
                        output.append((row["file_id"], score))
                return output

            if visual_ranking:
                # Preserve agreement between lexical and semantic branches. Collapsing
                # them into one list first gives every weak OCR hit a second full vote
                # from CLIP and crowds unrelated screenshots above strong text matches.
                file_rankings = [files_for(branch) for branch in text_branches]
                weights = [1.0] * len(file_rankings)
                if reranked:
                    file_rankings = [files_for(text_ranking)]
                    weights = [float(max(1, len(text_branches)))]
                file_rankings.append(files_for(visual_ranking))
                weights.append(1.0 if request.filters.modality in {"image", "video"} else 0.35)
                files = rrf(file_rankings, weights)
            else:
                files = files_for(text_ranking)
            result = []
            hashes = set()
            lexical_ids = (
                {i for i, _ in text_branches[0]}
                if request.mode != "semantic" and request.channels != "vision" and text_branches
                else set()
            )
            lexical_files = {by_id[i]["file_id"] for i in lexical_ids if i in by_id}
            text_ids = {i for i, _ in text_ranking}
            for file_id, score in files:
                hits: list[dict] = []
                for unit_id, _ in text_ranking + visual_ranking:
                    row = by_id.get(unit_id)
                    if (
                        row
                        and row["file_id"] == file_id
                        and all(
                            h["text_hash"] != row["text_hash"] or h["kind"] in {"image", "frame"}
                            for h in hits
                        )
                    ):
                        hits.append(row)
                if not hits:
                    continue
                best = hits[0]
                if best["sha256"] in hashes:
                    continue
                hashes.add(best["sha256"])
                aliases = self.store.rows(
                    """SELECT f.id,f.relative_path,f.path FROM files f JOIN file_revisions v ON v.id=f.active_revision_id
                  JOIN roots r ON r.id=f.root_id WHERE v.sha256=? AND f.status='ready' AND r.status='ready' AND r.enabled=1 AND f.id!=?""",
                    (best["sha256"], file_id),
                )
                aliases = [alias for alias in aliases if alias["id"] in allowed_files]
                result.append(
                    {
                        "file_id": file_id,
                        "name": best["name"],
                        "path": best["path"],
                        "relative_path": best["relative_path"],
                        "extension": best["extension"],
                        "modality": best["modality"],
                        "mtime_ns": best["mtime_ns"],
                        "size": best["size"],
                        "score": float(score),
                        "match_kind": "terms"
                        if file_id in lexical_files
                        else ("semantic" if any(h["id"] in text_ids for h in hits) else "visual"),
                        "ranking": "multimodal_rrf"
                        if visual_ranking
                        else (
                            "reranked" if reranked else "lexical" if keyword_only else request.mode
                        ),
                        "evidence": [evidence(h) for h in hits[:3]],
                        "aliases": aliases,
                        "warnings": json.loads(best["warnings"]),
                    }
                )
                if len(result) >= request.limit:
                    break
        return {
            "query": request.query,
            "results": result,
            "warnings": warnings,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "mode": request.mode,
        }
