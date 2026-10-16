"""The fake Brain's HTTP layer: the routes of `ENDPOINTS`, and every error as an `ApiError`."""

from typing import Annotated

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
from starlette.exceptions import HTTPException

from scrubgpt_contracts.mock_brain import logic
from scrubgpt_contracts.models.brain_api import (
    ENDPOINTS,
    MAX_AUDIO_BYTES,
    AskRequest,
    BriefingRequest,
    EmbedRequest,
    ExtractRequest,
    TranscribeForm,
    TranslateRequest,
)
from scrubgpt_contracts.models.common import (
    CONTRACT_VERSION,
    ERROR_HTTP_STATUS,
    ErrorCode,
    api_error,
)


class BrainError(Exception):
    """An error the fake Brain answers with an `ApiError` body."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _error(code: ErrorCode, message: str) -> JSONResponse:
    body = api_error(code, message).model_dump(mode="json")
    return JSONResponse(body, status_code=ERROR_HTTP_STATUS[code])


def _ok(body: BaseModel) -> JSONResponse:
    return JSONResponse(body.model_dump(mode="json", by_alias=True))


def _describe(errors: list) -> str:
    """Up to three validation errors as one English line."""
    parts = []
    for err in errors[:3]:
        where = ".".join(str(part) for part in err.get("loc", ()) if part != "body") or "body"
        parts.append(f"{where}: {str(err.get('msg', 'invalid')).removeprefix('Value error, ')}")
    more = f" (+{len(errors) - 3} more)" if len(errors) > 3 else ""
    return "invalid request: " + "; ".join(parts) + more


def create_app() -> FastAPI:
    """The fake Brain: the same endpoints and shapes as the real Brain, deterministic (D-037)."""
    app = FastAPI(
        title="ScrubGPT fake Brain",
        version=CONTRACT_VERSION,
        description="Deterministic stand-in for the Brain API (plan §4.4, §4.5; D-025, D-037).",
    )
    paths = {name: endpoint.path for name, endpoint in ENDPOINTS.items()}

    @app.exception_handler(RequestValidationError)
    async def _invalid(_: Request, exc: RequestValidationError) -> JSONResponse:
        # §4.1: FastAPI's 422 validation error is 400 bad_request.
        return _error(ErrorCode.BAD_REQUEST, _describe(list(exc.errors())))

    @app.exception_handler(HTTPException)
    async def _http(_: Request, exc: HTTPException) -> JSONResponse:
        if exc.status_code == 404:
            return _error(ErrorCode.NOT_FOUND, "no such endpoint")
        if exc.status_code == 413:
            return _error(ErrorCode.PAYLOAD_TOO_LARGE, str(exc.detail))
        return _error(ErrorCode.BAD_REQUEST, f"HTTP {exc.status_code}: {exc.detail}")

    @app.exception_handler(BrainError)
    async def _brain(_: Request, exc: BrainError) -> JSONResponse:
        return _error(exc.code, exc.message)

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
        return _error(ErrorCode.UNAVAILABLE, f"the fake Brain failed: {type(exc).__name__}")

    @app.get(paths["health"])
    def health() -> JSONResponse:
        return _ok(logic.health())

    @app.post(paths["transcribe"])
    async def transcribe(
        audio: Annotated[UploadFile, File()],
        lang_hint: Annotated[str, Form()],
        answer_id: Annotated[str, Form()],
    ) -> JSONResponse:
        try:
            form = TranscribeForm.model_validate({"lang_hint": lang_hint, "answer_id": answer_id})
        except ValidationError as exc:
            raise RequestValidationError(exc.errors(include_url=False)) from None
        # Any content type is accepted: clients guess it from the file name (D-037, issue #5).
        data = await audio.read(MAX_AUDIO_BYTES + 1)
        if len(data) > MAX_AUDIO_BYTES:
            raise BrainError(
                ErrorCode.PAYLOAD_TOO_LARGE, f"audio is larger than {MAX_AUDIO_BYTES} bytes"
            )
        if not data:
            raise BrainError(ErrorCode.BAD_REQUEST, "audio is empty")
        return _ok(logic.transcribe(form))

    @app.post(paths["extract"])
    def extract(body: ExtractRequest) -> JSONResponse:
        return _ok(logic.extract(body))

    @app.post(paths["translate"])
    def translate(body: TranslateRequest) -> JSONResponse:
        return _ok(logic.translate(body))

    @app.post(paths["embed"])
    def embed(body: EmbedRequest) -> JSONResponse:
        return _ok(logic.embed(body))

    @app.post(paths["ask"])
    def ask(body: AskRequest) -> JSONResponse:
        return _ok(logic.ask(body))

    @app.post(paths["briefing"])
    def briefing(body: BriefingRequest) -> JSONResponse:
        return _ok(logic.briefing(body))

    return app
