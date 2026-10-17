"""The OpenAI gateway (brain/CLAUDE.md rule 1; D-070): every OpenAI call of the Brain goes through
here, so model choice, retries, caching, cost and failure checks are handled in one place.

**Tiers, not model names.** Callers ask for a tier (`VISION_FAST`, `TEXT_SMART`, …, plan §3.1).
The gateway resolves it from the environment (`.env`): `<TIER>_MODEL`, e.g. `VISION_FAST_MODEL`.
An unknown tier, or a tier whose variable is unset or blank, is an error. No model name is
written in code. The resolved tier and model go into each result's `generated_by`, which becomes
the provenance of whatever the call produced.

**Requests** are the JSON body of an OpenAI endpoint without `model` (the gateway adds it):
by default the Responses API (`endpoint="responses"`).

**Cache** (`CACHE_MODE`, rule 1). The key is the SHA-256 of the canonical JSON of the endpoint
and the full body: model, input, schema and every parameter. One file per key goes under
`<cache_dir>/openai/` (default `<DATA_DIR>/cache/`, a relative `DATA_DIR` resolving against the
repo root).
- `readwrite` reads and writes;
- `readonly` reads and never writes (the offline demo: a miss still calls the transport, and the
  answer is not stored);
- `off` neither reads nor writes.

A hit makes no call. Refusals, truncated answers and failures are never cached.

**Retries.** Transient failures are retried with exponential backoff (`backoff_s`, doubling, or
the server's `Retry-After` when longer), up to `max_retries` times: 429, 5xx, and timeouts or lost
connections. Any other 4xx is not retried. The last error reaches the caller.

**Checks** before anything is cached or returned:
- a refusal (a `refusal` output item or message, or a content-filter stop) raises `RefusalError`;
- a truncated answer (`status: incomplete` for `max_output_tokens`, or `finish_reason: length`)
  raises `TruncatedError`;
- a failed response raises `GatewayError`.

**Cost.** Every call is logged (`CallLog`): tier, model, input, cached-input and output tokens,
cost, cache hit, attempts. Prices per million tokens come from configuration (`load_prices`; by
default `brain/config/openai_prices.yaml`, filled in on setup day from OpenAI's price list). A
model without a price gets cost `None` and a warning: prices are never guessed. A cache hit costs
0.

**Transport.** Injectable (`Transport`), so tests use a stub: no key is read and no socket is
opened. The default `HttpTransport` reads `OPENAI_API_KEY` on its first call only. Batch calls
(rule 5) and audio uploads (D2) come with the stages that need them.
"""

import hashlib
import json
import logging
import math
import os
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

import yaml
from scrubgpt_contracts.models.common import GeneratedBy

from scrubgpt_brain.engines.rulebook import KNOWLEDGE_DIR

REPO_ROOT = KNOWLEDGE_DIR.parent
TIERS = (
    "VISION_FAST",
    "VISION_DEEP",
    "TEXT_SMART",
    "TEXT_FAST",
    "STT",
    "STT_DIARIZE",
    "TTS",
    "EMBED",
)
"""The model tiers of plan §3.1 and `.env.example`; each is set as `<TIER>_MODEL`."""
CacheMode = Literal["readwrite", "readonly", "off"]
CACHE_MODES: tuple[CacheMode, ...] = ("readwrite", "readonly", "off")
PRICES_FILE = REPO_ROOT / "brain" / "config" / "openai_prices.yaml"
API_BASE = "https://api.openai.com/v1"
MAX_RETRIES = 4
BACKOFF_S = 1.0

log = logging.getLogger("scrubgpt_brain.openai")


class GatewayError(RuntimeError):
    """A call could not give a usable answer, or the gateway is misconfigured."""


class TransportError(GatewayError):
    """The transport failed: `status` is the HTTP status, or `None` for a timeout or a lost
    connection."""

    def __init__(self, message: str, *, status: int | None, retry_after_s: float | None = None):
        super().__init__(message)
        self.status = status
        self.retry_after_s = retry_after_s

    @property
    def transient(self) -> bool:
        return self.status is None or self.status == 429 or self.status >= 500


class RefusalError(GatewayError):
    """The model refused, or a content filter stopped the answer."""


class TruncatedError(GatewayError):
    """The answer was cut off (the output-token limit)."""


class Transport(Protocol):
    def __call__(self, endpoint: str, body: Mapping[str, Any]) -> dict[str, Any]:
        """POST `body` to the endpoint and return the JSON answer, or raise `TransportError`."""
        ...


@dataclass(frozen=True)
class Price:
    """US dollars per million tokens."""

    input: float
    output: float
    cached_input: float | None = None
    """Defaults to `input` when the price list has no cached-input price."""


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int = 0


@dataclass(frozen=True)
class CallLog:
    """One line of the cost log."""

    tier: str
    model: str
    endpoint: str
    usage: Usage
    cost_usd: float | None
    cache_hit: bool
    attempts: int


@dataclass(frozen=True)
class GatewayResult:
    """One answer, with what produced it."""

    tier: str
    model: str
    response: dict[str, Any]
    """The endpoint's JSON answer, as OpenAI sent it (or as cached)."""
    text: str | None
    """The answer's text (all output text of a Responses answer; a chat answer's message)."""
    usage: Usage
    cost_usd: float | None
    cache_hit: bool

    def generated_by(self, prompt_version: str | None) -> GeneratedBy:
        """The provenance `generated_by` for what this answer produced."""
        return GeneratedBy(model_tier=self.tier, model=self.model, prompt_version=prompt_version)

    def json(self) -> Any:
        """The answer text parsed as JSON (structured outputs)."""
        if self.text is None:
            raise GatewayError("the answer has no text to parse")
        return json.loads(self.text)


def load_prices(path: Path = PRICES_FILE) -> dict[str, Price]:
    """The price list: a YAML mapping `model: {input, output, cached_input?}` in US dollars per
    million tokens. A missing file is an empty list. Raises `GatewayError` for a malformed one."""
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        prices = {
            str(model): Price(
                input=float(p["input"]),
                output=float(p["output"]),
                cached_input=None if p.get("cached_input") is None else float(p["cached_input"]),
            )
            for model, p in data.items()
        }
    except (yaml.YAMLError, AttributeError, KeyError, TypeError, ValueError) as exc:
        raise GatewayError(f"{path}: not a price list ({exc!r})") from None
    for model, price in prices.items():
        values = [price.input, price.output, price.cached_input or 0.0]
        if not all(math.isfinite(v) and v >= 0 for v in values):
            raise GatewayError(f"{path}: {model}: prices must be numbers >= 0")
    return prices


def request_key(endpoint: str, body: Mapping[str, Any]) -> str:
    """The cache key: SHA-256 of the canonical JSON of the endpoint and the full body."""
    canonical = json.dumps(
        {"endpoint": endpoint, "body": body},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _usage(response: Mapping[str, Any]) -> Usage:
    usage = response.get("usage") or {}
    details = usage.get("input_tokens_details") or usage.get("prompt_tokens_details") or {}
    return Usage(
        input_tokens=int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0),
        output_tokens=int(usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0),
        cached_input_tokens=int(details.get("cached_tokens", 0) or 0),
    )


def _text(response: Mapping[str, Any]) -> str | None:
    if "output" in response:  # Responses API
        parts = [
            item.get("text", "")
            for out in response.get("output") or []
            for item in out.get("content") or []
            if item.get("type") == "output_text"
        ]
        return "".join(parts) if parts else None
    choices = response.get("choices") or []
    if choices:  # Chat Completions
        return (choices[0].get("message") or {}).get("content")
    return None


def check_response(response: Mapping[str, Any]) -> None:
    """Raise `RefusalError`, `TruncatedError` or `GatewayError` if the answer isn't usable."""
    status = response.get("status")
    if status == "failed":
        raise GatewayError(f"the response failed: {response.get('error')}")
    if status == "incomplete":
        reason = (response.get("incomplete_details") or {}).get("reason")
        if reason == "content_filter":
            raise RefusalError("a content filter stopped the answer")
        raise TruncatedError(f"the answer is incomplete ({reason or 'no reason given'})")
    for out in response.get("output") or []:
        if out.get("type") == "refusal":
            raise RefusalError(f"the model refused: {out.get('refusal')}")
        for item in out.get("content") or []:
            if item.get("type") == "refusal":
                raise RefusalError(f"the model refused: {item.get('refusal')}")
    for choice in response.get("choices") or []:
        message = choice.get("message") or {}
        if message.get("refusal"):
            raise RefusalError(f"the model refused: {message['refusal']}")
        if choice.get("finish_reason") == "content_filter":
            raise RefusalError("a content filter stopped the answer")
        if choice.get("finish_reason") == "length":
            raise TruncatedError("the answer was cut off at the output-token limit")


class HttpTransport:
    """The real transport: HTTPS to the OpenAI API with httpx. Reads `OPENAI_API_KEY` from the
    environment on its first call, never earlier."""

    def __init__(self, *, base_url: str = API_BASE, timeout_s: float = 120.0) -> None:
        self.base_url, self.timeout_s = base_url, timeout_s
        self._client: Any = None

    def __call__(self, endpoint: str, body: Mapping[str, Any]) -> dict[str, Any]:
        import httpx

        if self._client is None:
            key = os.environ.get("OPENAI_API_KEY", "").strip()
            if not key:
                raise GatewayError("OPENAI_API_KEY is not set (.env)")
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout_s,
                headers={"Authorization": f"Bearer {key}"},
            )
        try:
            answer = self._client.post(f"/{endpoint}", json=body)
        except httpx.TransportError as exc:  # timeouts and connection errors
            raise TransportError(f"{type(exc).__name__}: {exc}", status=None) from None
        if answer.status_code >= 400:
            retry_after = answer.headers.get("retry-after")
            try:
                message = answer.json()["error"]["message"]
            except (ValueError, KeyError, TypeError):
                message = answer.text[:500]
            raise TransportError(
                f"HTTP {answer.status_code}: {message}",
                status=answer.status_code,
                retry_after_s=float(retry_after) if retry_after and retry_after.isdigit() else None,
            )
        return answer.json()


class Gateway:
    """The one way the Brain calls OpenAI (see the module docstring)."""

    def __init__(
        self,
        *,
        env: Mapping[str, str] | None = None,
        transport: Transport | None = None,
        cache_dir: Path | None = None,
        cache_mode: CacheMode | None = None,
        prices: Mapping[str, Price] | None = None,
        max_retries: int = MAX_RETRIES,
        backoff_s: float = BACKOFF_S,
        sleep: Callable[[float], None] = time.sleep,
        on_call: Callable[[CallLog], None] | None = None,
    ) -> None:
        self.env = os.environ if env is None else env
        self.transport: Transport = transport if transport is not None else HttpTransport()
        mode = cache_mode or (self.env.get("CACHE_MODE") or "readwrite").strip()
        if mode not in CACHE_MODES:
            raise GatewayError(f"CACHE_MODE must be one of {', '.join(CACHE_MODES)}, not {mode!r}")
        self.cache_mode: CacheMode = mode  # type: ignore[assignment]
        self._cache_dir = cache_dir
        self.prices = load_prices() if prices is None else dict(prices)
        if max_retries < 0 or backoff_s < 0:
            raise GatewayError("max_retries and backoff_s must be >= 0")
        self.max_retries, self.backoff_s, self.sleep = max_retries, backoff_s, sleep
        self.on_call = on_call
        self.spent_usd = 0.0
        self._warned: set[str] = set()

    def model_for(self, tier: str) -> str:
        """The model a tier resolves to (`<TIER>_MODEL`)."""
        if tier not in TIERS:
            raise GatewayError(f"unknown model tier {tier!r}; the tiers are {', '.join(TIERS)}")
        model = (self.env.get(f"{tier}_MODEL") or "").strip()
        if not model:
            raise GatewayError(f"tier {tier}: set {tier}_MODEL in .env")
        return model

    @property
    def cache_dir(self) -> Path:
        """`<cache_dir>/openai`, by default `<DATA_DIR>/cache/openai`."""
        if self._cache_dir is None:
            data = (self.env.get("DATA_DIR") or "").strip()
            if not data:
                raise GatewayError("the cache needs a folder: set DATA_DIR or pass cache_dir")
            path = Path(data)
            self._cache_dir = (path if path.is_absolute() else REPO_ROOT / path) / "cache"
        return self._cache_dir / "openai"

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / key[:2] / f"{key}.json"

    def _read_cache(self, key: str) -> dict[str, Any] | None:
        if self.cache_mode == "off":
            return None
        path = self._cache_path(key)
        try:
            return json.loads(path.read_text(encoding="utf-8"))["response"]
        except FileNotFoundError:
            return None
        except (OSError, ValueError, KeyError, TypeError) as exc:
            log.warning("ignoring an unreadable cache entry %s: %s", path, exc)
            return None

    def _write_cache(self, key: str, endpoint: str, model: str, response: Mapping[str, Any]):
        if self.cache_mode != "readwrite":
            return
        path = self._cache_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = {"key": key, "endpoint": endpoint, "model": model, "response": response}
        handle, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{key[:8]}", suffix=".part")
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as file:
            json.dump(entry, file, ensure_ascii=False)
        os.replace(temp, path)

    def _send(self, endpoint: str, body: Mapping[str, Any]) -> tuple[dict[str, Any], int]:
        attempt = 0
        while True:
            attempt += 1
            try:
                return self.transport(endpoint, body), attempt
            except TransportError as exc:
                if not exc.transient or attempt > self.max_retries:
                    raise
                wait = max(self.backoff_s * 2 ** (attempt - 1), exc.retry_after_s or 0.0)
                log.warning(
                    "OpenAI %s failed (%s); retry %d in %.1f s", endpoint, exc, attempt, wait
                )
                self.sleep(wait)

    def cost(self, model: str, usage: Usage) -> float | None:
        """US dollars for one call, or `None` (with a warning, once per model) without a price."""
        price = self.prices.get(model)
        if price is None:
            if model not in self._warned:
                self._warned.add(model)
                log.warning("no price for model %s: its cost is not counted", model)
            return None
        cached = min(usage.cached_input_tokens, usage.input_tokens)
        cached_price = price.input if price.cached_input is None else price.cached_input
        dollars = (
            (usage.input_tokens - cached) * price.input
            + cached * cached_price
            + usage.output_tokens * price.output
        )
        return dollars / 1_000_000

    def call(
        self, tier: str, body: Mapping[str, Any], *, endpoint: str = "responses"
    ) -> GatewayResult:
        """Send one request at a model tier: from the cache if possible, else to OpenAI."""
        if "model" in body:
            raise GatewayError("pass a tier, not a model: the body must not set `model`")
        model = self.model_for(tier)
        request = {"model": model, **body}
        key = request_key(endpoint, request)
        cached = self._read_cache(key)
        if cached is not None:
            check_response(cached)
            usage = _usage(cached)
            result = GatewayResult(tier, model, cached, _text(cached), usage, 0.0, True)
            self._log(CallLog(tier, model, endpoint, usage, 0.0, True, 0))
            return result
        response, attempts = self._send(endpoint, request)
        usage = _usage(response)
        cost = self.cost(model, usage)
        if cost is not None:
            self.spent_usd += cost
        self._log(CallLog(tier, model, endpoint, usage, cost, False, attempts))
        check_response(response)  # a refusal or truncation is paid for, but never cached
        self._write_cache(key, endpoint, model, response)
        return GatewayResult(tier, model, response, _text(response), usage, cost, False)

    def _log(self, entry: CallLog) -> None:
        cost = "unknown" if entry.cost_usd is None else f"${entry.cost_usd:.6f}"
        log.info(
            "openai %s %s (%s): in %d (cached %d), out %d tokens, %s%s",
            entry.tier,
            entry.model,
            entry.endpoint,
            entry.usage.input_tokens,
            entry.usage.cached_input_tokens,
            entry.usage.output_tokens,
            cost,
            ", cache hit" if entry.cache_hit else f", {entry.attempts} attempt(s)",
        )
        if self.on_call is not None:
            self.on_call(entry)
