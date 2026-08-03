"""FastAPI application for secure local extraction jobs."""

from __future__ import annotations

import secrets
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, File, Form, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from chna_extractor import __version__
from chna_extractor.config import Settings, get_settings
from chna_extractor.errors import ChnaError
from chna_extractor.exporters import export_json, export_legacy_csv
from chna_extractor.logging import configure_logging, get_logger
from chna_extractor.models import (
    ApiConfig,
    ApiError,
    ExtractionMode,
    ExtractionResult,
    HealthResponse,
    JobResponse,
    ProgressEvents,
    ResultEditRequest,
)
from chna_extractor.security import save_upload
from chna_extractor.service import ExtractionService
from chna_extractor.storage import JobStore


def create_app(settings: Settings | None = None) -> FastAPI:
    selected = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        configure_logging(selected.log_level)
        store = JobStore(selected.database_path)
        await store.initialize()
        service = ExtractionService(selected, store)
        application.state.settings = selected
        application.state.store = store
        application.state.service = service
        await service.resume_pending()
        yield

    application = FastAPI(
        title="CHNA Extractor API",
        summary="Evidence-first extraction for Community Health Needs Assessment PDFs",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=selected.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type", "X-Request-ID"],
    )
    _add_middleware(application)
    _add_error_handlers(application)
    # Resolve once at startup so serving remains stable if the process working directory changes.
    # The explicit setting also works for non-editable installs where __file__ is in site-packages.
    selected_frontend = selected.frontend_dist.expanduser().resolve(strict=False)
    _add_routes(application, selected_frontend)
    if (selected_frontend / "assets").is_dir():
        application.mount(
            "/assets",
            StaticFiles(directory=selected_frontend / "assets"),
            name="frontend-assets",
        )
    return application


def _add_middleware(application: FastAPI) -> None:
    @application.middleware("http")
    async def secure_response_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID", secrets.token_hex(12))[:64]
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'"
        )
        if request.url.path.startswith("/api/v1/extractions"):
            response.headers["Cache-Control"] = "no-store"
        return response


def _add_error_handlers(application: FastAPI) -> None:
    @application.exception_handler(RequestValidationError)
    async def request_validation_handler(
        request: Request, _exc: RequestValidationError
    ) -> JSONResponse:
        payload = ApiError(
            error="The request did not match the required schema.",
            code="invalid_request",
            request_id=getattr(request.state, "request_id", None),
        )
        return JSONResponse(status_code=422, content=payload.model_dump(mode="json"))

    @application.exception_handler(ChnaError)
    async def chna_error_handler(request: Request, exc: ChnaError) -> JSONResponse:
        payload = ApiError(
            error=exc.user_message,
            code=exc.code,
            request_id=getattr(request.state, "request_id", None),
        )
        return JSONResponse(status_code=exc.status_code, content=payload.model_dump(mode="json"))

    @application.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        get_logger().error(
            "request_failed",
            request_id=getattr(request.state, "request_id", None),
            exception_type=type(exc).__name__,
        )
        payload = ApiError(
            error="An unexpected error occurred. Use the request ID when reviewing local logs.",
            code="internal_error",
            request_id=getattr(request.state, "request_id", None),
        )
        return JSONResponse(status_code=500, content=payload.model_dump(mode="json"))


def _add_routes(application: FastAPI, frontend_dist: Path) -> None:
    index_file = frontend_dist / "index.html" if (frontend_dist / "index.html").is_file() else None
    mark_file = frontend_dist / "mark.svg" if (frontend_dist / "mark.svg").is_file() else None

    @application.get("/", include_in_schema=False)
    async def root() -> Response:
        if index_file is not None:
            return FileResponse(index_file)
        return JSONResponse({"name": "CHNA Extractor", "docs": "/docs", "health": "/healthz"})

    @application.get("/mark.svg", include_in_schema=False)
    async def frontend_mark() -> Response:
        if mark_file is not None:
            return FileResponse(mark_file, media_type="image/svg+xml")
        return Response(status_code=404)

    @application.get("/healthz", response_model=HealthResponse, tags=["operations"])
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", version=__version__)

    @application.get("/readyz", response_model=HealthResponse, tags=["operations"])
    async def readiness(request: Request) -> Response:
        ready = await _store(request).is_ready()
        payload = HealthResponse(status="ready" if ready else "not_ready", version=__version__)
        return JSONResponse(
            status_code=200 if ready else 503, content=payload.model_dump(mode="json")
        )

    @application.get("/api/v1/config", response_model=ApiConfig, tags=["configuration"])
    async def public_config(request: Request) -> ApiConfig:
        settings = _settings(request)
        return ApiConfig(
            offline_demo_available=settings.fixture_path.exists(),
            live_available=settings.live_available,
            max_upload_mb=settings.max_upload_mb,
            model=settings.openai_model,
            optional_features={
                "ocr": settings.enable_ocr,
                "google_maps": settings.enable_google_maps,
                "web_search": settings.enable_web_search,
            },
        )

    @application.post(
        "/api/v1/extractions", response_model=JobResponse, status_code=202, tags=["extractions"]
    )
    async def create_extraction(
        request: Request,
        file: Annotated[UploadFile, File(description="A bounded CHNA PDF")],
        mode: Annotated[ExtractionMode, Form()] = ExtractionMode.AUTO,
    ) -> JobResponse:
        upload = await save_upload(file, _settings(request))
        return await _service(request).submit(upload, mode)

    @application.post(
        "/api/v1/extractions/demo",
        response_model=JobResponse,
        status_code=202,
        tags=["extractions"],
    )
    async def create_demo_extraction(request: Request) -> JobResponse:
        return await _service(request).submit_demo()

    @application.get(
        "/api/v1/extractions/{job_id}", response_model=JobResponse, tags=["extractions"]
    )
    async def get_extraction(job_id: str, request: Request) -> JobResponse:
        return await _store(request).get_job(job_id)

    @application.get(
        "/api/v1/extractions/{job_id}/events",
        response_model=ProgressEvents,
        tags=["extractions"],
    )
    async def get_extraction_events(job_id: str, request: Request) -> ProgressEvents:
        return await _store(request).get_events(job_id)

    @application.get(
        "/api/v1/extractions/{job_id}/result",
        response_model=ExtractionResult,
        tags=["extractions"],
    )
    async def get_extraction_result(job_id: str, request: Request) -> ExtractionResult:
        return await _store(request).get_result(job_id)

    @application.patch(
        "/api/v1/extractions/{job_id}/result",
        response_model=ExtractionResult,
        tags=["extractions"],
    )
    async def update_extraction_result(
        job_id: str, edit: ResultEditRequest, request: Request
    ) -> ExtractionResult:
        return await _store(request).update_result(job_id, edit)

    @application.get(
        "/api/v1/extractions/{job_id}/export", response_class=Response, tags=["extractions"]
    )
    async def export_extraction(
        job_id: str,
        request: Request,
        format: Annotated[Literal["json", "csv"], Query()] = "json",
    ) -> Response:
        result = await _store(request).get_result(job_id)
        if format == "csv":
            return Response(
                export_legacy_csv(result),
                media_type="text/csv; charset=utf-8",
                headers={"Content-Disposition": f'attachment; filename="chna-{job_id[:8]}.csv"'},
            )
        return Response(
            export_json(result),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="chna-{job_id[:8]}.json"'},
        )


def _settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


def _store(request: Request) -> JobStore:
    return request.app.state.store  # type: ignore[no-any-return]


def _service(request: Request) -> ExtractionService:
    return request.app.state.service  # type: ignore[no-any-return]


app = create_app()
