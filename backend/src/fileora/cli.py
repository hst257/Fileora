from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from fileora.config import Settings
from fileora.domain import FileoraError
from fileora.evaluation import run_evaluation
from fileora.models import Models, prepare_model
from fileora.resources import peak_rss_bytes
from fileora.retrieval import SearchRequest
from fileora.service import InstanceLock, Service


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="fileora", description="Private local file search")
    result.add_argument("--data-dir", type=Path, help="Runtime catalog, models, indexes and assets")
    result.add_argument("--models-dir", type=Path, help="Optional shared prepared model directory")
    result.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    result.add_argument(
        "--text-model",
        choices=("sentence-transformers/all-MiniLM-L6-v2", "BAAI/bge-small-en-v1.5"),
        default="sentence-transformers/all-MiniLM-L6-v2",
    )
    result.add_argument("--ocr", action="store_true", help="Run local Tesseract OCR")
    result.add_argument("--vision", action="store_true", help="Create and search CLIP embeddings")
    result.add_argument(
        "--media",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Override the saved audio/video processing preference for this run",
    )
    result.add_argument("--chunk-tokens", type=int, default=192)
    result.add_argument("--overlap-tokens", type=int, default=32)
    result.add_argument(
        "--ppt-ocr-seconds",
        type=float,
        default=20,
        help="Optional slide-image OCR budget per presentation (0–45 seconds)",
    )
    result.add_argument(
        "--ppt-ocr-max-images",
        type=int,
        default=48,
        help="Maximum unique slide images to OCR per presentation",
    )
    sub = result.add_subparsers(dest="command", required=True)
    roots = sub.add_parser("roots")
    roots_sub = roots.add_subparsers(dest="action", required=True)
    add = roots_sub.add_parser("add")
    add.add_argument("path")
    add.add_argument("--exclude", action="append", default=[])
    roots_sub.add_parser("list")
    remove = roots_sub.add_parser("forget")
    remove.add_argument("id", type=int)
    index = sub.add_parser("index")
    index.add_argument("--verify", action="store_true")
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument(
        "--watch",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Override the saved automatic-update preference for this run",
    )
    serve.add_argument("--ollama-model", default="qwen3:4b")
    search = sub.add_parser("search")
    search.add_argument("query")
    search.add_argument("--mode", choices=("semantic", "lexical", "hybrid"), default="hybrid")
    search.add_argument("--limit", type=int, default=10)
    models = sub.add_parser("models")
    models_sub = models.add_subparsers(dest="action", required=True)
    download = models_sub.add_parser("download")
    download.add_argument("model")
    download.add_argument("--revision", help="Optional explicit Hugging Face commit")
    models_sub.add_parser("list")
    sub.add_parser("doctor")
    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("--queries", type=Path, default=Path("evaluation/queries.jsonl"))
    evaluate.add_argument("--judgments", type=Path, default=Path("evaluation/judgments.jsonl"))
    evaluate.add_argument("--mode", choices=("semantic", "lexical", "hybrid"), default="hybrid")
    evaluate.add_argument("--split", choices=("dev", "test"))
    evaluate.add_argument("--rerank", action="store_true")
    evaluate.add_argument("--repeat", type=int, default=3)
    evaluate.add_argument("--output", type=Path, default=Path("evaluation/reports/latest.json"))
    return result


def main() -> None:
    args = parser().parse_args()
    settings_kwargs = {
        "device": args.device,
        "text_model": args.text_model,
        "enable_ocr": args.ocr,
        "enable_vision": args.vision,
        "enable_media": args.media,
        "chunk_tokens": args.chunk_tokens,
        "overlap_tokens": args.overlap_tokens,
        "ppt_ocr_seconds": args.ppt_ocr_seconds,
        "ppt_ocr_max_images": args.ppt_ocr_max_images,
    }
    if args.data_dir:
        settings_kwargs["data_dir"] = args.data_dir
    if args.models_dir:
        settings_kwargs["models_dir"] = args.models_dir
    if args.command == "serve":
        settings_kwargs["watch"] = args.watch
    settings = Settings(**settings_kwargs)
    settings.prepare()
    output: Any
    try:
        if args.command == "models":
            if args.action == "download":
                instance = InstanceLock(settings.data_dir / "instance.lock")
                instance.acquire()
                try:
                    output = prepare_model(settings, args.model, args.revision)
                finally:
                    instance.release()
            else:
                output = [
                    json.loads(p.read_text(encoding="utf-8"))
                    for p in (settings.models_dir or settings.data_dir / "models").glob(
                        "*/fileora-manifest.json"
                    )
                ]
            print(json.dumps(output, indent=2))
            return
        if args.command == "serve":
            import uvicorn

            from fileora.api import create_app

            settings.ollama_model = args.ollama_model
            uvicorn.run(
                create_app(settings), host="127.0.0.1", port=args.port, workers=1, access_log=False
            )
            return
        service = Service(settings)
        service.instance.acquire()
        try:
            if args.command == "roots":
                if args.action == "add":
                    output = service.indexer.add_root(args.path, args.exclude)
                elif args.action == "forget":
                    service.indexer.forget_root(args.id)
                    output = {"forgotten": args.id}
                else:
                    output = service.store.rows("SELECT * FROM roots")
            elif args.command == "index":
                started = time.perf_counter()
                output = service.indexer.run(service.indexer.create_job(args.verify))
                seconds = time.perf_counter() - started
                output.update(
                    seconds=round(seconds, 3), files_per_second=output["indexed"] / seconds
                )
                output["peak_parent_rss_bytes"] = peak_rss_bytes()
                output["errors"] = service.store.rows(
                    "SELECT relative_path,code,message FROM job_errors WHERE job_id=?",
                    (output["id"],),
                )
                if output["state"] == "failed" or output["failed"]:
                    print(json.dumps(output, indent=2))
                    sys.exit(1)
            elif args.command == "search":
                output = service.search.run(
                    SearchRequest(query=args.query, mode=args.mode, limit=args.limit)
                )
            elif args.command == "evaluate":
                if args.repeat < 0:
                    raise FileoraError("INVALID_REPEAT", "Repeat must be nonnegative")
                output = run_evaluation(
                    service,
                    args.queries,
                    args.judgments,
                    args.mode,
                    args.split,
                    args.rerank,
                    args.repeat,
                )
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(output, indent=2), encoding="utf-8")
                output = {
                    "report": str(args.output),
                    "metrics": output["metrics"],
                    "warm_p95_ms": output["warm_p95_ms"],
                }
            else:
                import shutil

                output = {
                    "python": sys.version.split()[0],
                    "data_dir": str(settings.data_dir),
                    "text_model_prepared": Models(settings).available(settings.text_model),
                    "tesseract": bool(shutil.which("tesseract")),
                    "catalog": service.store.status(),
                }
            print(json.dumps(output, indent=2, ensure_ascii=False))
        finally:
            service.instance.release()
    except FileoraError as exc:
        print(json.dumps({"error": {"code": exc.code, "message": exc.message}}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
