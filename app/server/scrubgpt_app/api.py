"""The app server's HTTP API (I1): cases, Procedure References and media for the web app.

The web app talks only to this server (app/web/CLAUDE.md rule 1). JSON bodies pass contract
models through unchanged (`by_alias`, so `class` stays `class`), with both `ja` and `en`
(app/server/CLAUDE.md rule 10). Every error is an `ApiError` body (plan §4.1); the UI localises by
`code`. Media is served with HTTP Range support, so the player can seek and play at 8–16× (rule 7).

| Method and path | Body |
|---|---|
| `GET /api/health` | status, `contract_version`, `brain_mode`, loaded / rejected counts |
| `GET /api/cases` | `{"cases": [CaseSummary]}` in case-id order |
| `GET /api/cases/{case_id}` | a `CaseSummary` plus every package document |
| `GET /api/catalog` | loaded ids, rejected packages and references with their problems |
| `GET /api/references/{procedure_id}` | the Procedure Reference |
| `GET /media/cases/{case_id}/{path}` | `video.mp4`, `poster.jpg`, `clips/…`, `thumbs/…` |

With a built web app (`app/web/dist`), every other `GET` serves it (single-page app).
"""

import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from scrubgpt_contracts.models.common import (
    CONTRACT_VERSION,
    ERROR_HTTP_STATUS,
    ErrorCode,
    api_error,
)
from starlette.exceptions import HTTPException

from scrubgpt_app.catalog import Catalog, LoadedCase, scan
from scrubgpt_app.settings import Settings

MEDIA_FILES = re.compile(
    r"^(video\.mp4|poster\.jpg|clips/[A-Za-z0-9._-]+\.(mp4|jpg)|thumbs/[A-Za-z0-9._-]+\.(jpg|png))$"
)
"""The package files the media route serves (plan §4.2); nothing else in a case folder."""

MEDIA_TYPES = {".mp4": "video/mp4", ".jpg": "image/jpeg", ".png": "image/png"}

ERROR_BY_STATUS = {404: ErrorCode.NOT_FOUND, 413: ErrorCode.PAYLOAD_TOO_LARGE}


class AppError(Exception):
    """An error the server answers with an `ApiError` body."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def error_response(code: ErrorCode, message: str) -> JSONResponse:
    body = api_error(code, message).model_dump(mode="json")
    return JSONResponse(body, status_code=ERROR_HTTP_STATUS[code])


def dump(model: Any) -> Any:
    return model.model_dump(mode="json", by_alias=True) if model is not None else None


def media_url(case_id: str, name: str) -> str:
    return f"/media/cases/{case_id}/{name}"


def summary(loaded: LoadedCase) -> dict[str, Any]:
    """What the case list shows (J1): `case.json`, media URLs, counts and trust badges."""
    return {
        "case": dump(loaded.case),
        "media": {
            "video": media_url(loaded.id, "video.mp4"),
            "poster": media_url(loaded.id, "poster.jpg"),
        },
        "counts": loaded.counts(),
        "trust_labels": [label.value for label in loaded.trust_labels()],
        "has_metrics": loaded.metrics is not None,
    }


def detail(loaded: LoadedCase) -> dict[str, Any]:
    return summary(loaded) | {
        "timeline": dump(loaded.timeline),
        "moments": dump(loaded.moments),
        "questions": dump(loaded.questions),
        "seed_records": dump(loaded.seed_records),
        "metrics": dump(loaded.metrics),
    }


def create_app(settings: Settings, catalog: Catalog | None = None) -> FastAPI:
    """The app server. `catalog` defaults to a scan of `settings.data_dir` at start-up."""
    app = FastAPI(
        title="ScrubGPT app server",
        version=CONTRACT_VERSION,
        description="Cases, Procedure References and media for the ScrubGPT web app (plan §2.9).",
    )
    app.state.settings = settings
    app.state.catalog = catalog if catalog is not None else scan(settings.data_dir)

    def current() -> Catalog:
        return app.state.catalog

    def find_case(case_id: str) -> LoadedCase:
        loaded = current().cases.get(case_id)
        if loaded is None:
            raise AppError(ErrorCode.NOT_FOUND, f"no loaded case {case_id!r}")
        return loaded

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return error_response(exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def _invalid(_: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(ErrorCode.BAD_REQUEST, f"invalid request: {exc.errors()[:3]}")

    @app.exception_handler(HTTPException)
    async def _http(_: Request, exc: HTTPException) -> JSONResponse:
        code = ERROR_BY_STATUS.get(exc.status_code, ErrorCode.BAD_REQUEST)
        message = "no such path" if code is ErrorCode.NOT_FOUND else str(exc.detail)
        return error_response(code, message)

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        catalog = current()
        return {
            "status": "ok",
            "contract_version": CONTRACT_VERSION,
            "brain_mode": settings.brain_mode.value,
            "cases": {"loaded": len(catalog.cases), "rejected": len(catalog.rejected)},
        }

    @app.get("/api/cases")
    def cases() -> dict[str, Any]:
        catalog = current()
        return {"cases": [summary(catalog.cases[key]) for key in sorted(catalog.cases)]}

    @app.get("/api/cases/{case_id}")
    def case(case_id: str) -> dict[str, Any]:
        return detail(find_case(case_id))

    @app.get("/api/catalog")
    def catalog_report() -> dict[str, Any]:
        catalog = current()

        def rejected(items: list) -> list[dict[str, Any]]:
            return [{"path": item.path.name, "problems": list(item.problems)} for item in items]

        return {
            "data_dir": str(catalog.data_dir),
            "loaded": [
                {"case_id": key, "warnings": list(catalog.cases[key].warnings)}
                for key in sorted(catalog.cases)
            ],
            "rejected": rejected(catalog.rejected),
            "references": sorted(catalog.references),
            "rejected_references": rejected(catalog.rejected_references),
        }

    @app.get("/api/references/{procedure_id}")
    def reference(procedure_id: str) -> Any:
        found = current().references.get(procedure_id)
        if found is None:
            raise AppError(ErrorCode.NOT_FOUND, f"no Procedure Reference {procedure_id!r}")
        return dump(found)

    @app.get("/media/cases/{case_id}/{name:path}")
    def media(case_id: str, name: str) -> FileResponse:
        loaded = find_case(case_id)
        if not MEDIA_FILES.match(name):
            raise AppError(ErrorCode.NOT_FOUND, f"{name!r} is not a media file of a case")
        folder = loaded.folder.resolve()
        path = (folder / name).resolve()
        if not path.is_relative_to(folder) or not path.is_file():
            raise AppError(ErrorCode.NOT_FOUND, f"case {case_id} has no {name}")
        # FileResponse answers Range requests with 206 Partial Content (seeking, 8–16× play).
        return FileResponse(path, media_type=MEDIA_TYPES[path.suffix])

    _serve_web(app, settings.web_dist)
    return app


def _serve_web(app: FastAPI, dist: Path) -> None:
    """Serve the built web app at `/` (offline demo), with every unknown page → `index.html`."""
    index = dist / "index.html"
    if not index.is_file():
        return
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{page:path}", include_in_schema=False)
    def web(page: str) -> FileResponse:
        if page.startswith(("api/", "media/")):
            raise AppError(ErrorCode.NOT_FOUND, "no such path")
        candidate = (dist / page).resolve()
        if page and candidate.is_relative_to(dist.resolve()) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)
