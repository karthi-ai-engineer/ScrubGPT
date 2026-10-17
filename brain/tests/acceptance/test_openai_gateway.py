"""OpenAI gateway (no feature ID): #17 acceptance criteria 11-16 (Team Lead answer and its
condition 4; D-070; brain/CLAUDE.md rule 1; brain/README.md "OpenAI gateway"; the
`engines/openai_gateway.py` docstring).

**No OpenAI at all** (#17 condition 4): an autouse fixture removes `OPENAI_API_KEY` from the
environment and makes every socket connection fail; every call goes to a stub transport.

Expected behaviour, written from the spec before the code was opened:
11. Tiers come from environment variables (`<TIER>_MODEL`, the `.env` tier names); an unknown or
    unset tier raises a clear error; no model name is hard-coded.
12. The transport is injectable; with a stub no key is read and no socket is opened.
13. Transient errors (429, 5xx, timeouts) are retried with backoff (injectable sleep) up to a
    configurable limit; other 4xx are not retried; the final error reaches the caller.
14. The cache key is a stable hash of the full request (model, messages, schema, parameters);
    the cache lives under `<cache_dir>` (default `<DATA_DIR>/cache/`); `readwrite` reads and
    writes, `readonly` reads and never writes (a miss calls the transport, writes nothing), `off`
    neither; a hit makes no transport call.
15. Each call logs the tier, the model, input and output tokens and the cost; prices come from
    configuration; an unknown price gives cost `null` with a warning, never a guess.
16. A refusal or a truncation (e.g. `finish_reason: length`, or a refusal field) raises a typed
    error and is never written to the cache.

Responses follow OpenAI's documented shapes (Responses API, and Chat Completions for
`finish_reason`); model names are synthetic.
"""

from __future__ import annotations

import ast
import json
import logging
import re
import socket
from pathlib import Path

import pytest
from scrubgpt_brain.engines import openai_gateway as gw
from scrubgpt_brain.engines.openai_gateway import (
    Gateway,
    GatewayError,
    HttpTransport,
    Price,
    RefusalError,
    TransportError,
    TruncatedError,
    check_response,
    load_prices,
    request_key,
)

ENV = {"VISION_FAST_MODEL": "t1-vision-model", "TEXT_SMART_MODEL": "t1-text-model"}
BODY = {
    "input": [{"role": "user", "content": [{"type": "input_text", "text": "Which step?"}]}],
    "text": {"format": {"type": "json_schema", "name": "step", "strict": True,
                        "schema": {"type": "object", "properties": {"step": {"type": "string"}},
                                   "required": ["step"], "additionalProperties": False}}},
    "temperature": 0,
}  # fmt: skip


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """#17 C12 / condition 4: no key in the environment and no socket can connect."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def refuse(*args, **kwargs):
        raise AssertionError("a gateway test tried to open a network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def responses_answer(text='{"step": "x"}', *, input_tokens=1000, output_tokens=200, cached=0,
                     **overrides) -> dict:  # fmt: skip
    """A completed OpenAI Responses API answer."""
    answer = {
        "id": "resp_t1", "object": "response", "status": "completed", "model": "t1-vision-model",
        "output": [{"type": "message", "role": "assistant", "status": "completed",
                    "content": [{"type": "output_text", "text": text, "annotations": []}]}],
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens,
                  "input_tokens_details": {"cached_tokens": cached},
                  "output_tokens_details": {"reasoning_tokens": 0},
                  "total_tokens": input_tokens + output_tokens},
    }  # fmt: skip
    answer.update(overrides)
    return answer


class Stub:
    """A transport: answers from a queue (dicts are answers, exceptions are raised)."""

    def __init__(self, *answers) -> None:
        self.answers = list(answers) or [responses_answer()]
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, endpoint, body):
        self.calls.append((endpoint, json.loads(json.dumps(body))))
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, BaseException):
            raise answer
        return json.loads(json.dumps(answer))


def gateway(tmp_path, transport, **kw) -> Gateway:
    kw.setdefault("env", ENV)
    kw.setdefault("cache_dir", tmp_path / "cache")
    kw.setdefault("cache_mode", "readwrite")
    kw.setdefault("prices", {})
    kw.setdefault("sleep", lambda s: None)
    return Gateway(transport=transport, **kw)


def cache_files(tmp_path) -> list[Path]:
    root = tmp_path / "cache"
    return sorted(p for p in root.rglob("*") if p.is_file()) if root.exists() else []


# ── criterion 11 ─────────────────────────────────────────────────────────────


def test_g11_a_tier_resolves_from_the_environment(tmp_path):
    """#17 C11 "Tiers are resolved from environment variables (the `.env` tier names)" (README:
    `<TIER>_MODEL`): the model goes into the request and the result, and into `generated_by`."""
    stub = Stub()
    g = gateway(tmp_path, stub)
    assert g.model_for("VISION_FAST") == "t1-vision-model"
    result = g.call("VISION_FAST", BODY)
    assert stub.calls[0][1]["model"] == "t1-vision-model"
    assert {k: v for k, v in stub.calls[0][1].items() if k != "model"} == BODY
    assert (result.tier, result.model) == ("VISION_FAST", "t1-vision-model")
    gen = result.generated_by("step_window.v1")
    assert (gen.model_tier, gen.model, gen.prompt_version) == (
        "VISION_FAST", "t1-vision-model", "step_window.v1"
    )  # fmt: skip
    assert result.json() == {"step": "x"}


def test_g11_the_process_environment_is_the_default(tmp_path, monkeypatch):
    """#17 C11 "resolved from environment variables": without `env=`, the process environment
    (where `.env` is loaded) is read."""
    monkeypatch.setenv("TEXT_FAST_MODEL", "t1-from-the-environment")
    g = Gateway(transport=Stub(), cache_dir=tmp_path / "c", cache_mode="off", prices={})
    assert g.model_for("TEXT_FAST") == "t1-from-the-environment"


@pytest.mark.parametrize(
    ("tier", "env", "needle"),
    [
        ("SUPER_FAST", ENV, "SUPER_FAST"),
        ("TEXT_FAST", ENV, "TEXT_FAST_MODEL"),
        ("VISION_DEEP", {**ENV, "VISION_DEEP_MODEL": "   "}, "VISION_DEEP_MODEL"),
        ("vision_fast", ENV, "vision_fast"),
    ],
    ids=["unknown", "unset", "blank", "lower-case"],
)
def test_g11_an_unknown_or_unset_tier_is_a_clear_error(tmp_path, tier, env, needle):
    """#17 C11 "An unknown or unset tier raises a clear error": `GatewayError` naming the tier or
    its variable, before any transport call."""
    stub = Stub()
    g = gateway(tmp_path, stub, env=env)
    with pytest.raises(GatewayError) as caught:
        g.call(tier, BODY)
    assert needle in str(caught.value), caught.value
    assert stub.calls == []


def test_g11_a_body_that_names_a_model_is_refused(tmp_path):
    """#17 C11 "No model name is hard-coded" (README: "a call names a tier"): a request body
    that sets `model` itself is refused, so callers can't bypass the tiers."""
    stub = Stub()
    with pytest.raises(GatewayError):
        gateway(tmp_path, stub).call("VISION_FAST", {**BODY, "model": "t1-direct"})
    assert stub.calls == []


def test_g11_no_model_name_is_written_in_the_gateways_code(const):
    """#17 C11 "No model name is hard-coded": no string in the gateway module's code
    (docstrings aside) looks like an OpenAI model name (gpt-…, o1/o3/o4…, whisper, tts-…,
    text-embedding-…, dall-e, chatgpt), and the committed price list names no model yet."""
    path = Path(gw.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docstrings.add(id(body[0].value))
    model_like = re.compile(
        r"\b(gpt-|o[134](-|\b)|whisper|tts-1|text-embedding|dall-e|chatgpt)", re.I
    )
    hits = [
        f"line {n.lineno}: {n.value!r}"
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings
        and model_like.search(n.value)
    ]  # fmt: skip
    assert not hits, hits
    assert load_prices(const.repo_root / "brain" / "config" / "openai_prices.yaml") == {}


# ── criterion 12 ─────────────────────────────────────────────────────────────


class NoKeyEnv(dict):
    """An env mapping that fails the test if anyone reads `OPENAI_API_KEY` from it."""

    def __getitem__(self, key):
        assert key != "OPENAI_API_KEY", "the gateway read OPENAI_API_KEY"
        return super().__getitem__(key)

    def get(self, key, default=None):
        assert key != "OPENAI_API_KEY", "the gateway read OPENAI_API_KEY"
        return super().get(key, default)


def test_g12_a_stub_transport_answers_without_key_or_socket(tmp_path):
    """#17 C12 "The transport is injectable. In tests a stub answers, and no key is read and no
    socket is opened (the test proves this …)": the key variable is unset (autouse), every socket
    connection fails (autouse), the env mapping fails on a key read, and the call succeeds
    through the stub."""
    stub = Stub()
    g = gateway(tmp_path, stub, env=NoKeyEnv(ENV))
    assert g.call("VISION_FAST", BODY).text == '{"step": "x"}'
    assert len(stub.calls) == 1 and stub.calls[0][0] == "responses"


def test_g12_the_default_transport_needs_the_key_only_when_it_sends(tmp_path):
    """README "The default sends HTTPS with httpx and reads `OPENAI_API_KEY` only on its first
    call": building a gateway with the default transport reads no key and opens no socket; its
    first call, with no key set, fails with a `GatewayError` naming the key, before any
    connection (the socket guard would fail the test otherwise)."""
    g = Gateway(env=NoKeyEnv(ENV), cache_dir=tmp_path / "c", cache_mode="off", prices={})
    assert isinstance(g.transport, HttpTransport)
    with pytest.raises(GatewayError) as caught:
        g.call("VISION_FAST", BODY)
    assert "OPENAI_API_KEY" in str(caught.value)


def test_g12_an_endpoint_can_be_chosen(tmp_path):
    """README/docstring: the body goes to the Responses API by default (`endpoint="responses"`),
    and to another endpoint when named; the stub sees which."""
    stub = Stub({"choices": [{"index": 0, "finish_reason": "stop",
                              "message": {"role": "assistant", "content": "ok"}}],
                 "usage": {"prompt_tokens": 10, "completion_tokens": 2}})  # fmt: skip
    result = gateway(tmp_path, stub).call(
        "TEXT_SMART", {"messages": []}, endpoint="chat/completions"
    )
    assert stub.calls[0][0] == "chat/completions"
    assert result.text == "ok"


# ── criterion 13 ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("status", [429, 500, 502, 503, None], ids=lambda s: f"status-{s}")
def test_g13_transient_errors_are_retried_with_backoff(tmp_path, status):
    """#17 C13 "transient errors (429, 5xx, timeouts) are retried with backoff up to a
    configurable limit (the sleep is injectable)" (README: "doubling backoff"): two failures,
    then an answer: three transport calls, sleeps of 0.5 and 1.0 s, and the answer comes back."""
    sleeps: list[float] = []
    stub = Stub(TransportError("t1 transient", status=status),
                TransportError("t1 transient", status=status), responses_answer())  # fmt: skip
    g = gateway(tmp_path, stub, backoff_s=0.5, sleep=sleeps.append)
    result = g.call("VISION_FAST", BODY)
    assert len(stub.calls) == 3
    assert sleeps == [0.5, 1.0]
    assert result.text == '{"step": "x"}'


def test_g13_a_longer_retry_after_is_honoured(tmp_path):
    """README "(or the server's `Retry-After`)": a 429 asking for 7 s waits 7 s, not the 0.5 s
    backoff."""
    sleeps: list[float] = []
    stub = Stub(TransportError("slow down", status=429, retry_after_s=7.0), responses_answer())
    gateway(tmp_path, stub, backoff_s=0.5, sleep=sleeps.append).call("VISION_FAST", BODY)
    assert sleeps == [7.0]


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_g13_other_4xx_errors_are_not_retried(tmp_path, status):
    """#17 C13 "Non-transient 4xx errors are not retried. The final error comes through to the
    caller": one transport call, no sleep, the `TransportError` (with its status) is raised."""
    sleeps: list[float] = []
    stub = Stub(TransportError(f"HTTP {status}", status=status))
    with pytest.raises(TransportError) as caught:
        gateway(tmp_path, stub, sleep=sleeps.append).call("VISION_FAST", BODY)
    assert caught.value.status == status
    assert len(stub.calls) == 1 and sleeps == []


@pytest.mark.parametrize("limit", [0, 2])
def test_g13_the_retry_limit_is_configurable_and_the_last_error_comes_through(tmp_path, limit):
    """#17 C13 "up to a configurable limit … The final error comes through to the caller": with
    `max_retries` 0 or 2 and a server that keeps failing, 1 or 3 calls, then its error."""
    sleeps: list[float] = []
    stub = Stub(TransportError("down", status=503))
    g = gateway(tmp_path, stub, max_retries=limit, backoff_s=1.0, sleep=sleeps.append)
    with pytest.raises(TransportError) as caught:
        g.call("VISION_FAST", BODY)
    assert caught.value.status == 503
    assert len(stub.calls) == limit + 1
    assert sleeps == [1.0 * 2**k for k in range(limit)]
    assert cache_files(tmp_path) == []


def test_g13_the_default_limit_is_four_retries(tmp_path):
    """README "up to 4 times": the default gateway makes 5 attempts against a server that keeps
    failing."""
    stub = Stub(TransportError("down", status=500))
    with pytest.raises(TransportError):
        Gateway(env=ENV, transport=stub, cache_dir=tmp_path / "c", cache_mode="off", prices={},
                sleep=lambda s: None).call("VISION_FAST", BODY)  # fmt: skip
    assert len(stub.calls) == 5


# ── criterion 14 ─────────────────────────────────────────────────────────────


def test_g14_the_key_is_a_stable_hash_of_the_full_request():
    """#17 C14 "the key is a stable hash of the full request (model, messages, schema,
    parameters)": the same request in another key order gives the same key; a change in the
    model, a message, the schema, a parameter or the endpoint gives another."""
    request = {"model": "m1", **BODY}
    key = request_key("responses", request)
    assert re.fullmatch(r"[0-9a-f]{64}", key)
    reordered = json.loads(json.dumps(dict(reversed(list(request.items())))))
    assert request_key("responses", reordered) == key
    changed = [
        {**request, "model": "m2"},
        {**request, "input": [{"role": "user", "content": [{"type": "input_text", "text": "?"}]}]},
        {**request, "text": {"format": {"type": "json_schema", "name": "other", "strict": True,
                                        "schema": {"type": "object"}}}},
        {**request, "temperature": 0.2},
        {**request, "max_output_tokens": 100},
    ]  # fmt: skip
    keys = {request_key("responses", r) for r in changed} | {
        request_key("chat/completions", request)
    }
    assert key not in keys and len(keys) == len(changed) + 1


def test_g14_readwrite_reads_and_writes_and_a_hit_makes_no_call(tmp_path):
    """#17 C14 "`CACHE_MODE=readwrite` reads and writes … A cache hit makes no transport call"
    (README: "A hit makes no call and costs nothing"): the second identical call is served from
    `<cache_dir>/openai/`, with no transport call, `cache_hit` true and cost 0."""
    stub = Stub()
    g = gateway(tmp_path, stub, prices={"t1-vision-model": Price(input=2.0, output=8.0)})
    first = g.call("VISION_FAST", BODY)
    files = cache_files(tmp_path)
    assert len(files) == 1 and (tmp_path / "cache" / "openai") in files[0].parents
    second = g.call("VISION_FAST", BODY)
    assert len(stub.calls) == 1
    assert (first.cache_hit, second.cache_hit) == (False, True)
    assert second.response == first.response and second.text == first.text
    assert second.cost_usd == 0
    other = gateway(tmp_path, Stub())  # a new gateway on the same folder reads it too
    assert other.call("VISION_FAST", BODY).cache_hit is True


def test_g14_readonly_reads_but_never_writes(tmp_path):
    """#17 C14 "`readonly` reads and never writes (a miss calls the transport but writes
    nothing)": a miss calls the stub and leaves the cache empty; an entry written earlier by a
    `readwrite` gateway is read without a call."""
    stub = Stub()
    ro = gateway(tmp_path, stub, cache_mode="readonly")
    assert ro.call("VISION_FAST", BODY).cache_hit is False
    assert len(stub.calls) == 1 and cache_files(tmp_path) == []
    gateway(tmp_path, Stub(), cache_mode="readwrite").call("TEXT_SMART", BODY)
    files_before = cache_files(tmp_path)
    reader = Stub()
    result = gateway(tmp_path, reader, cache_mode="readonly").call("TEXT_SMART", BODY)
    assert result.cache_hit is True and reader.calls == []
    assert cache_files(tmp_path) == files_before


def test_g14_off_neither_reads_nor_writes(tmp_path):
    """#17 C14 "`off` neither reads nor writes": with an entry in the cache, an `off` gateway
    still calls the transport, and writes nothing new."""
    gateway(tmp_path, Stub(), cache_mode="readwrite").call("VISION_FAST", BODY)
    before = {p: p.read_bytes() for p in cache_files(tmp_path)}
    stub = Stub()
    g = gateway(tmp_path, stub, cache_mode="off")
    assert g.call("VISION_FAST", BODY).cache_hit is False
    assert g.call("TEXT_SMART", BODY).cache_hit is False
    assert len(stub.calls) == 2
    assert {p: p.read_bytes() for p in cache_files(tmp_path)} == before


def test_g14_cache_mode_and_folder_come_from_the_environment(tmp_path):
    """#17 C14 "The cache lives under `<cache_dir>` (default `<DATA_DIR>/cache/`)" and
    `CACHE_MODE` (README "CACHE_MODE, DATA_DIR/cache"): with neither `cache_dir` nor `cache_mode`
    passed, `DATA_DIR` and `CACHE_MODE` decide; an invalid mode is an error."""
    data = tmp_path / "data"
    env = {**ENV, "DATA_DIR": str(data), "CACHE_MODE": "readonly"}
    stub = Stub()
    g = Gateway(env=env, transport=stub, prices={}, sleep=lambda s: None)
    assert g.cache_mode == "readonly"
    g.call("VISION_FAST", BODY)
    assert not data.exists() or not [p for p in data.rglob("*") if p.is_file()]
    g = Gateway(env={**env, "CACHE_MODE": "readwrite"}, transport=Stub(), prices={})
    g.call("VISION_FAST", BODY)
    written = [p for p in data.rglob("*") if p.is_file()]
    assert len(written) == 1 and (data / "cache") in written[0].parents
    with pytest.raises(GatewayError):
        Gateway(env={**env, "CACHE_MODE": "sometimes"}, transport=Stub(), prices={})


def test_g14_a_missing_cache_folder_is_a_clear_error(tmp_path):
    """#17 C14 "default `<DATA_DIR>/cache/`": with no `DATA_DIR` and no `cache_dir`, a cached
    mode can't work and says so (an error naming `DATA_DIR`), before any transport call."""
    stub = Stub()
    g = Gateway(env=ENV, transport=stub, cache_mode="readwrite", prices={})
    with pytest.raises(GatewayError) as caught:
        g.call("VISION_FAST", BODY)
    assert "DATA_DIR" in str(caught.value)


# ── criterion 15 ─────────────────────────────────────────────────────────────


def test_g15_each_call_logs_tier_model_tokens_and_cost(tmp_path, caplog):
    """#17 C15 "Each call logs the tier, the model, input and output tokens, and the cost. Prices
    come from configuration": `on_call` gets a `CallLog` per call (a miss, then a hit), the
    logger `scrubgpt_brain.openai` writes a line, and the cost follows the price list (OpenAI
    usage semantics: cached tokens are part of the input tokens)."""
    logs = []
    prices = {"t1-vision-model": Price(input=2.0, output=8.0, cached_input=0.5)}
    stub = Stub(responses_answer(input_tokens=1000, output_tokens=200, cached=400))
    g = gateway(tmp_path, stub, prices=prices, on_call=logs.append)
    with caplog.at_level(logging.INFO, logger="scrubgpt_brain.openai"):
        result = g.call("VISION_FAST", BODY)
        g.call("VISION_FAST", BODY)
    want = (600 * 2.0 + 400 * 0.5 + 200 * 8.0) / 1_000_000
    assert result.cost_usd == pytest.approx(want, abs=1e-12)
    assert [(e.tier, e.model, e.cache_hit) for e in logs] == [
        ("VISION_FAST", "t1-vision-model", False), ("VISION_FAST", "t1-vision-model", True)
    ]  # fmt: skip
    assert (logs[0].usage.input_tokens, logs[0].usage.output_tokens) == (1000, 200)
    assert logs[0].usage.cached_input_tokens == 400
    assert logs[0].cost_usd == pytest.approx(want) and logs[1].cost_usd == 0
    assert g.spent_usd == pytest.approx(want)
    lines = [r.getMessage() for r in caplog.records if r.name == "scrubgpt_brain.openai"]
    assert len(lines) >= 2 and "VISION_FAST" in lines[0] and "t1-vision-model" in lines[0]


def test_g15_an_unknown_price_is_null_with_a_warning(tmp_path, caplog):
    """#17 C15 "When a model's price is unknown, cost is `null` with a warning; prices are never
    guessed": an empty price list gives cost `None` in the result and the log, a warning, and no
    spend."""
    logs = []
    g = gateway(tmp_path, Stub(), prices={}, on_call=logs.append)
    with caplog.at_level(logging.WARNING, logger="scrubgpt_brain.openai"):
        result = g.call("VISION_FAST", BODY)
    assert result.cost_usd is None and logs[0].cost_usd is None
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("t1-vision-model" in r.getMessage() for r in warnings), warnings
    assert g.spent_usd == 0


def test_g15_prices_are_read_from_a_price_list_file(tmp_path):
    """#17 C15 "Prices come from configuration" (README: `brain/config/openai_prices.yaml`, US
    dollars per million tokens, `cached_input` optional): `load_prices` reads such a file; a
    missing file is an empty list and a malformed one an error."""
    path = tmp_path / "prices.yaml"
    path.write_text("t1-a: {input: 1.25, output: 10.0, cached_input: 0.125}\n"
                    "t1-b: {input: 0.4, output: 1.6}\n", encoding="utf-8")  # fmt: skip
    prices = load_prices(path)
    assert prices["t1-a"] == Price(input=1.25, output=10.0, cached_input=0.125)
    assert prices["t1-b"].input == 0.4 and prices["t1-b"].output == 1.6
    assert prices["t1-b"].cached_input is None
    assert load_prices(tmp_path / "none.yaml") == {}
    for bad in ("t1-a: {input: 1.0}\n", "t1-a: {input: -1, output: 1}\n", "- not a mapping\n"):
        path.write_text(bad, encoding="utf-8")
        with pytest.raises(GatewayError):
            load_prices(path)


# ── criterion 16 ─────────────────────────────────────────────────────────────

REFUSALS = {
    "responses-refusal-item": responses_answer(output=[{
        "type": "message", "role": "assistant", "status": "completed",
        "content": [{"type": "refusal", "refusal": "I can't help with that."}]}]),
    "responses-content-filter": responses_answer(
        status="incomplete", incomplete_details={"reason": "content_filter"}),
    "chat-refusal-field": {"choices": [{"index": 0, "finish_reason": "stop", "message": {
        "role": "assistant", "content": None, "refusal": "I can't help with that."}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 3}},
    "chat-content-filter": {"choices": [{"index": 0, "finish_reason": "content_filter",
        "message": {"role": "assistant", "content": ""}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 0}},
}  # fmt: skip
TRUNCATIONS = {
    "responses-max-output-tokens": responses_answer(
        status="incomplete", incomplete_details={"reason": "max_output_tokens"}),
    "chat-finish-reason-length": {"choices": [{"index": 0, "finish_reason": "length",
        "message": {"role": "assistant", "content": '{"step": "x'}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 50}},
}  # fmt: skip


@pytest.mark.parametrize(
    ("answer", "error"),
    [(a, RefusalError) for a in REFUSALS.values()]
    + [(a, TruncatedError) for a in TRUNCATIONS.values()],
    ids=[*REFUSALS, *TRUNCATIONS],
)  # fmt: skip
def test_g16_refusal_and_truncation_raise_typed_errors_and_are_never_cached(tmp_path, answer,
                                                                             error):  # fmt: skip
    """#17 C16 "Refusal and truncation (e.g. `finish_reason: length`, or a refusal field) raise
    typed errors and are **never written to the cache**": the typed error is raised, the cache
    stays empty, and the next identical call asks the transport again."""
    stub = Stub(answer)
    g = gateway(tmp_path, stub)
    endpoint = "chat/completions" if "choices" in answer else "responses"
    for _ in range(2):
        with pytest.raises(error):
            g.call("VISION_FAST", BODY, endpoint=endpoint)
    assert len(stub.calls) == 2
    assert cache_files(tmp_path) == []
    assert issubclass(error, GatewayError)


def test_g16_check_response_classifies_answers():
    """#17 C16 with `check_response`: a completed answer passes; refusals raise `RefusalError`,
    truncations `TruncatedError`, a failed response `GatewayError`."""
    check_response(responses_answer())
    for answer in REFUSALS.values():
        with pytest.raises(RefusalError):
            check_response(answer)
    for answer in TRUNCATIONS.values():
        with pytest.raises(TruncatedError):
            check_response(answer)
    with pytest.raises(GatewayError):
        check_response(responses_answer(status="failed", error={"message": "server error"}))


def test_g16_a_failed_response_is_not_cached(tmp_path):
    """Docstring "Refusals, truncated answers and failures are never cached": a `failed`
    response raises `GatewayError` and leaves the cache empty."""
    stub = Stub(responses_answer(status="failed", error={"code": "server_error"}))
    with pytest.raises(GatewayError):
        gateway(tmp_path, stub).call("VISION_FAST", BODY)
    assert cache_files(tmp_path) == []
