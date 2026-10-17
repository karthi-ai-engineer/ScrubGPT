"""The Brain client (I7): the app server's only way to the Brain API (plan §4.4).

`BRAIN_MODE=mock` calls the fake Brain (`MOCK_BRAIN_URL`, :8101), `real` the Brain API
(`BRAIN_URL`, :8100); both serve the same endpoints and shapes, so nothing else changes. Requests
and responses are the contract models from `ENDPOINTS`, validated both ways, so a Brain that
answers off-contract is an error here, never a silent pass-through. Every failure is a
`BrainError` carrying an `ApiError` code; 503/504 (and an unreachable Brain) are what the UI shows
as "Brain unavailable" (app/server/CLAUDE.md rule 1).
"""

from collections.abc import Mapping
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError
from scrubgpt_contracts.models.brain_api import (
    ENDPOINTS,
    ExtractRequest,
    ExtractResponse,
    TranscribeForm,
    TranscribeResponse,
    TranslateRequest,
    TranslateResponse,
)
from scrubgpt_contracts.models.common import ApiError, ErrorCode

from scrubgpt_app.settings import BrainMode, Settings

UNAVAILABLE_CODES = frozenset({ErrorCode.UNAVAILABLE, ErrorCode.TIMEOUT})
"""Codes the UI shows as "Brain unavailable" (with a typed or tap answer as the fallback)."""


class BrainError(Exception):
    """The Brain could not give a valid answer. `code` is an `ApiError` code."""

    def __init__(self, code: ErrorCode, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable

    @property
    def unavailable(self) -> bool:
        return self.code in UNAVAILABLE_CODES


class BrainClient:
    """Typed calls to the Brain API."""

    def __init__(
        self,
        base_url: str,
        *,
        transport: httpx.BaseTransport | None = None,
        mode: str = "",
        http: httpx.Client | None = None,
    ) -> None:
        """`http` replaces the HTTP client (tests pass a FastAPI `TestClient` of the fake Brain,
        which is an `httpx.Client`); `transport` replaces only its transport."""
        self.base_url = base_url.rstrip("/")
        self.mode = mode
        self._http = http or httpx.Client(base_url=self.base_url, transport=transport)

    @classmethod
    def from_settings(
        cls, settings: Settings, *, transport: httpx.BaseTransport | None = None
    ) -> "BrainClient":
        url = (
            settings.mock_brain_url if settings.brain_mode is BrainMode.MOCK else settings.brain_url
        )
        return cls(url, transport=transport, mode=settings.brain_mode.value)

    def close(self) -> None:
        self._http.close()

    def _call[M: BaseModel](
        self,
        name: str,
        response_model: type[M],
        *,
        json: Any = None,
        data: Mapping[str, str] | None = None,
        files: Mapping[str, tuple[str, bytes, str]] | None = None,
    ) -> M:
        endpoint = ENDPOINTS[name]
        try:
            response = self._http.request(
                endpoint.method,
                endpoint.path,
                json=json,
                data=data,
                files=files,
                timeout=endpoint.timeout_s,
            )
        except httpx.TimeoutException:
            raise BrainError(
                ErrorCode.TIMEOUT, f"the Brain did not answer {name} in time", retryable=True
            ) from None
        except httpx.TransportError as exc:
            raise BrainError(
                ErrorCode.UNAVAILABLE,
                f"the Brain at {self.base_url} can't be reached ({type(exc).__name__})",
                retryable=True,
            ) from None
        if response.status_code != 200:
            raise _error_from(name, response)
        try:
            return response_model.model_validate_json(response.content)
        except ValidationError as exc:
            raise BrainError(
                ErrorCode.UPSTREAM_ERROR,
                f"the Brain's {name} response breaks the contract: {exc.errors()[:2]}",
            ) from None

    def health(self) -> dict[str, Any]:
        model = ENDPOINTS["health"].response
        return self._call("health", model).model_dump(mode="json")

    def transcribe(
        self, form: TranscribeForm, audio: bytes, filename: str, content_type: str
    ) -> TranscribeResponse:
        fields = {key: str(value) for key, value in form.model_dump(mode="json").items()}
        return self._call(
            "transcribe",
            TranscribeResponse,
            data=fields,
            files={"audio": (filename, audio, content_type)},
        )

    def extract(self, request: ExtractRequest) -> ExtractResponse:
        body = request.model_dump(mode="json", by_alias=True)
        return self._call("extract", ExtractResponse, json=body)

    def translate(self, request: TranslateRequest) -> TranslateResponse:
        return self._call("translate", TranslateResponse, json=request.model_dump(mode="json"))


def _error_from(name: str, response: httpx.Response) -> BrainError:
    """The Brain's `ApiError` body as a `BrainError`; anything else as `upstream_error`."""
    try:
        body = ApiError.model_validate_json(response.content)
    except ValidationError:
        if response.status_code in (503, 504):
            code = ErrorCode.UNAVAILABLE if response.status_code == 503 else ErrorCode.TIMEOUT
            return BrainError(code, f"the Brain answered {name} with HTTP {response.status_code}")
        return BrainError(
            ErrorCode.UPSTREAM_ERROR,
            f"the Brain answered {name} with HTTP {response.status_code} and no ApiError body",
        )
    error = body.error
    return BrainError(error.code, error.message, retryable=error.retryable)
