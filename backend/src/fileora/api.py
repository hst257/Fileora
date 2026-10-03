from __future__ import annotations

import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from fileora.assistant import answer
from fileora.config import (
    AUDIO_EXTENSIONS,
    IMAGE_EXTENSIONS,
    PRESENTATION_EXTENSIONS,
    VIDEO_EXTENSIONS,
    VISION_MODEL,
    Settings,
)
from fileora.domain import FileoraError
from fileora.extraction import ocr_capability
from fileora.retrieval import SearchRequest
from fileora.service import Service


class RootRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4096)
    exclusions: list[str] = Field(default_factory=list, max_length=100)


class JobRequest(BaseModel):
    verify: bool = False


class WatchRequest(BaseModel):
    enabled: bool


def create_app(settings: Settings | None = None, service: Service | None = None) -> FastAPI:
    service = service or Service(settings or Settings())
    token = secrets.token_urlsafe(32)

    @asynccontextmanager
    async def lifespan(app):
        service.instance.acquire()
        try:
            for profile in service.store.rows("SELECT * FROM embedding_profiles"):
                service.indexes.get(profile)
            service.worker.start()
            yield
        finally:
            service.worker.stop()
            service.instance.release()

    app = FastAPI(
        title="Fileora local API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.service = service

    # FastAPI's default docs load a CDN and inline JavaScript. Keep documentation
    # usable offline under the same CSP as the application.
    app.mount(
        "/api/docs-assets",
        StaticFiles(directory=service.settings.frontend_dir / "api-docs", check_dir=False),
        name="api-docs-assets",
    )

    @app.get("/api/docs", include_in_schema=False)
    def api_docs():
        return HTMLResponse("""<!doctype html><html lang="en"><head><meta charset="utf-8">
        <meta name="viewport" content="width=device-width,initial-scale=1"><title>Fileora API</title>
        <link rel="stylesheet" href="/api/docs-assets/swagger-ui.css"></head>
        <body><div id="swagger-ui"></div><script src="/api/docs-assets/swagger-ui-bundle.js"></script>
        <script src="/api/docs-init.js"></script></body></html>""")

    @app.get("/api/docs-init.js", include_in_schema=False)
    def docs_script():
        return Response(
            """fetch('/api/v1/session').then(r => r.json()).then(session => {
          SwaggerUIBundle({url: '/api/openapi.json', dom_id: '#swagger-ui', validatorUrl: null,
            presets: [SwaggerUIBundle.presets.apis],
            requestInterceptor: request => {
              if (!['GET', 'HEAD', 'OPTIONS'].includes((request.method || 'GET').toUpperCase()))
                request.headers['X-Fileora-Token'] = session.token;
              return request;
            }
          });
        });""",
            media_type="application/javascript",
        )

    @app.middleware("http")
    async def local_security(request: Request, call_next):
        host = request.url.hostname
        origin = request.headers.get("origin")
        if host not in {"localhost", "127.0.0.1", "::1"}:
            return JSONResponse(
                {"error": {"code": "INVALID_HOST", "message": "Only loopback hosts are allowed"}},
                status_code=403,
            )
        if origin and origin != str(request.base_url).rstrip("/"):
            return JSONResponse(
                {"error": {"code": "INVALID_ORIGIN", "message": "Cross-origin access is blocked"}},
                status_code=403,
            )
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse(
                {
                    "error": {
                        "code": "CROSS_SITE_BLOCKED",
                        "message": "Cross-site access is blocked",
                    }
                },
                status_code=403,
            )
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not secrets.compare_digest(
            request.headers.get("x-fileora-token", ""), token
        ):
            return JSONResponse(
                {
                    "error": {
                        "code": "INVALID_SESSION",
                        "message": "Refresh Fileora to start a valid local session",
                    }
                },
                status_code=403,
            )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; media-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; object-src 'self'; frame-ancestors 'none'"
        )
        return response

    @app.exception_handler(FileoraError)
    async def application_error(request, exc):
        return JSONResponse(
            {"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status
        )

    @app.get("/api/v1/session")
    def session():
        return {"token": token}

    @app.get("/api/v1/health")
    def health():
        data_path = str(service.settings.data_dir).replace("'", "''")
        model_path = str(service.settings.models_dir).replace("'", "''")
        ocr = ocr_capability(service.settings)
        return {
            "status": "ready",
            "offline": True,
            "text_model": service.settings.text_model,
            "semantic_ready": service.models.available(service.settings.text_model),
            "device": service.models.device,
            "vision_enabled": service.settings.enable_vision,
            "vision_ready": service.settings.enable_vision
            and service.models.available(VISION_MODEL),
            "ocr_enabled": service.settings.enable_ocr,
            "ocr_ready": ocr["ready"],
            "ocr_engine": ocr["engine"],
            "media_enabled": service.settings.enable_media,
            "watch": service.worker.watch_status(),
            "model_setup_command": f"fileora --data-dir '{data_path}' --models-dir '{model_path}' models download {service.settings.text_model}",
        }

    @app.get("/api/v1/index/status")
    def status():
        return service.store.status()

    @app.get("/api/v1/index/watch")
    def watch_status():
        return service.worker.watch_status()

    @app.put("/api/v1/index/watch")
    def configure_watch(request: WatchRequest):
        return service.configure_watch(request.enabled)

    @app.post("/api/v1/search")
    def search(request: SearchRequest):
        return service.search.run(request)

    @app.get("/api/v1/roots")
    def roots():
        return service.store.rows("SELECT * FROM roots ORDER BY id")

    @app.post("/api/v1/roots", status_code=201)
    def add_root(request: RootRequest):
        root = service.indexer.add_root(request.path, request.exclusions)
        if service.settings.watch:
            service.worker.restart_watch()
        return root

    @app.delete("/api/v1/roots/{root_id}", status_code=204)
    def forget(root_id: int):
        if service.store.one("SELECT id FROM jobs WHERE state IN ('queued','running')"):
            raise FileoraError(
                "INDEX_BUSY", "Cancel or finish indexing before forgetting a folder", 409
            )
        if not service.store.one("SELECT id FROM roots WHERE id=?", (root_id,)):
            raise FileoraError("NOT_FOUND", "Folder not found", 404)
        service.indexer.forget_root(root_id)
        if service.settings.watch:
            service.worker.restart_watch()
        return Response(status_code=204)

    @app.post("/api/v1/index/jobs", status_code=202)
    def submit(request: JobRequest):
        if service.store.one("SELECT id FROM jobs WHERE state IN ('queued','running')"):
            raise FileoraError("INDEX_BUSY", "An indexing job is already queued or running", 409)
        return {"job_id": service.worker.submit(request.verify)}

    @app.get("/api/v1/jobs")
    def jobs():
        return service.store.rows("SELECT * FROM jobs ORDER BY created_at DESC,rowid DESC LIMIT 20")

    @app.get("/api/v1/jobs/{job_id}")
    def job(job_id: str):
        row = service.store.one("SELECT * FROM jobs WHERE id=?", (job_id,))
        if not row:
            raise FileoraError("NOT_FOUND", "Job not found", 404)
        row["errors"] = service.store.rows(
            "SELECT relative_path,code,message FROM job_errors WHERE job_id=? LIMIT 100", (job_id,)
        )
        return row

    @app.post("/api/v1/jobs/{job_id}/cancel", status_code=202)
    def cancel(job_id: str):
        if not service.store.one("SELECT id FROM jobs WHERE id=?", (job_id,)):
            raise FileoraError("NOT_FOUND", "Job not found", 404)
        service.store.execute(
            "UPDATE jobs SET cancel=1 WHERE id=? AND state IN ('queued','running')", (job_id,)
        )
        return {"status": "cancellation_requested"}

    @app.get("/api/v1/files/{file_id}")
    def file(file_id: int):
        return service.file(file_id)

    @app.get("/api/v1/files/{file_id}/preview")
    def preview(file_id: int):
        path, _ = service.source(file_id)
        if path.suffix.lower() == ".pdf":
            return FileResponse(path, media_type="application/pdf")
        if path.suffix.lower() in PRESENTATION_EXTENSIONS:
            content_type = (
                "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                if path.suffix.lower() == ".pptx"
                else "application/vnd.ms-powerpoint"
            )
            return FileResponse(path, media_type=content_type, filename=path.name)
        if path.suffix.lower() in IMAGE_EXTENSIONS | AUDIO_EXTENSIONS | VIDEO_EXTENSIONS:
            return FileResponse(path)
        from fileora.extraction import text_file

        return Response(text_file(path), media_type="text/plain; charset=utf-8")

    @app.get("/api/v1/assets/{chunk_id}")
    def asset(chunk_id: int):
        return FileResponse(service.asset(chunk_id), media_type="image/jpeg")

    @app.post("/api/v1/answer")
    def local_answer(request: SearchRequest):
        return answer(service, request)

    dist = service.settings.frontend_dir
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="frontend-assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.startswith("api/"):
            raise FileoraError("NOT_FOUND", "API route not found", 404)
        index = dist / "index.html"
        if index.is_file():
            return FileResponse(index, media_type="text/html")
        return JSONResponse(
            {
                "message": "Build the frontend with npm run build in frontend, then restart Fileora. API docs: /api/docs"
            },
            status_code=503,
        )

    return app
