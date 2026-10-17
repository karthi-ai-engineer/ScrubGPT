"""Dev1's unit tests for the OpenAI gateway (engines/openai_gateway.py; D-070 criteria 11-16).

A stub transport answers every call: no key is read, and opening a socket fails the test."""

import json
import logging
import socket
from pathlib import Path
from typing import Any

import pytest
from scrubgpt_brain.engines import openai_gateway as og

ENV = {"VISION_FAST_MODEL": "vision-model-a", "TEXT_SMART_MODEL": "text-model-b"}
BODY = {
    "input": [{"role": "user", "content": "Which step is this?"}],
    "text": {"format": {"type": "json_schema", "name": "s", "schema": {}, "strict": True}},
}


def answer(text: str = '{"step": "rarp.p03.s01"}', **changes: Any) -> dict[str, Any]:
    """A Responses API answer."""
    base = {
        "id": "resp_1",
        "status": "completed",
        "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}],
        "usage": {
            "input_tokens": 1000,
            "output_tokens": 200,
            "input_tokens_details": {"cached_tokens": 400},
        },
    }
    base.update(changes)
    return base


class Stub:
    """Answers from a script: each item is a dict (the answer) or an exception to raise."""

    def __init__(self, *script: Any) -> None:
        self.script = list(script)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, endpoint: str, body: Any) -> dict[str, Any]:
        self.calls.append((endpoint, dict(body)))
        item = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """No key, and no network: any socket fails the test."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def no_socket(*args, **kwargs):
        raise AssertionError("the gateway tried to open a socket")

    monkeypatch.setattr(socket, "socket", no_socket)
    monkeypatch.setattr(socket, "create_connection", no_socket)


def gateway(tmp_path: Path, stub: Stub, **kw: Any) -> og.Gateway:
    kw.setdefault("cache_dir", tmp_path / "cache")
    kw.setdefault("prices", {})
    kw.setdefault("sleep", lambda s: None)
    return og.Gateway(env=kw.pop("env", ENV), transport=stub, **kw)


# 11 · tiers ───────────────────────────────────────────────────────────────────


def test_tiers_resolve_from_the_environment(tmp_path: Path):
    g = gateway(tmp_path, Stub(answer()))
    assert g.model_for("VISION_FAST") == "vision-model-a"
    with pytest.raises(og.GatewayError, match="unknown model tier 'VISION'"):
        g.model_for("VISION")
    with pytest.raises(og.GatewayError, match="tier TEXT_FAST: set TEXT_FAST_MODEL in .env"):
        g.model_for("TEXT_FAST")
    blank = gateway(tmp_path, Stub(answer()), env={"VISION_FAST_MODEL": "  "})
    with pytest.raises(og.GatewayError, match="set VISION_FAST_MODEL"):
        blank.call("VISION_FAST", BODY)
    with pytest.raises(og.GatewayError, match="must not set `model`"):
        g.call("VISION_FAST", {**BODY, "model": "x"})


def test_a_call_sends_the_tier_model_and_returns_the_answer(tmp_path: Path):
    stub = Stub(answer())
    result = gateway(tmp_path, stub).call("VISION_FAST", BODY)
    assert stub.calls == [("responses", {"model": "vision-model-a", **BODY})]
    assert (result.tier, result.model, result.cache_hit) == ("VISION_FAST", "vision-model-a", False)
    assert result.json() == {"step": "rarp.p03.s01"}
    by = result.generated_by("step_window.v1")
    assert (by.model_tier, by.model, by.prompt_version) == (
        "VISION_FAST",
        "vision-model-a",
        "step_window.v1",
    )


# 12 · injectable transport, no key ────────────────────────────────────────────


def test_the_default_transport_reads_no_key_until_it_is_used(tmp_path: Path):
    g = og.Gateway(env=ENV, cache_dir=tmp_path, prices={})  # builds an HttpTransport
    assert isinstance(g.transport, og.HttpTransport)
    with pytest.raises(og.GatewayError, match="OPENAI_API_KEY is not set"):
        g.call("VISION_FAST", BODY)  # fails before any socket: no key


# 13 · retries ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("status", [429, 500, 503, None])
def test_transient_errors_are_retried_with_backoff(tmp_path: Path, status):
    waits: list[float] = []
    stub = Stub(
        og.TransportError("busy", status=status), og.TransportError("busy", status=status), answer()
    )
    result = gateway(tmp_path, stub, sleep=waits.append, backoff_s=0.5).call("VISION_FAST", BODY)
    assert result.text and len(stub.calls) == 3 and waits == [0.5, 1.0]


def test_retry_after_wins_when_longer(tmp_path: Path):
    waits: list[float] = []
    stub = Stub(og.TransportError("slow down", status=429, retry_after_s=7), answer())
    gateway(tmp_path, stub, sleep=waits.append).call("VISION_FAST", BODY)
    assert waits == [7.0]


def test_other_4xx_errors_are_not_retried_and_the_last_error_comes_through(tmp_path: Path):
    stub = Stub(og.TransportError("HTTP 400: bad schema", status=400))
    with pytest.raises(og.TransportError, match="bad schema"):
        gateway(tmp_path, stub).call("VISION_FAST", BODY)
    assert len(stub.calls) == 1
    always = Stub(og.TransportError("HTTP 503: down", status=503))
    with pytest.raises(og.TransportError, match="down") as info:
        gateway(tmp_path, always, max_retries=2).call("VISION_FAST", BODY)
    assert info.value.status == 503 and len(always.calls) == 3


# 14 · cache ───────────────────────────────────────────────────────────────────


def test_the_cache_key_covers_the_whole_request():
    key = og.request_key("responses", {"model": "m", **BODY})
    assert key == og.request_key("responses", {**BODY, "model": "m"})  # key order doesn't matter
    assert key != og.request_key("responses", {"model": "n", **BODY})
    assert key != og.request_key("responses", {"model": "m", **BODY, "temperature": 0})
    assert key != og.request_key("chat/completions", {"model": "m", **BODY})


def test_readwrite_stores_and_a_hit_makes_no_call(tmp_path: Path):
    stub = Stub(answer())
    g = gateway(tmp_path, stub)
    first = g.call("VISION_FAST", BODY)
    second = g.call("VISION_FAST", BODY)
    assert len(stub.calls) == 1 and second.cache_hit and second.response == first.response
    assert second.cost_usd == 0.0
    files = list((tmp_path / "cache" / "openai").rglob("*.json"))
    assert len(files) == 1 and not list((tmp_path / "cache").rglob("*.part"))
    assert json.loads(files[0].read_text("utf-8"))["model"] == "vision-model-a"
    # Another tier means another model, so another key.
    g.call("TEXT_SMART", BODY)
    assert len(stub.calls) == 2


def test_readonly_reads_but_never_writes(tmp_path: Path):
    gateway(tmp_path, Stub(answer("cached"))).call("VISION_FAST", BODY)
    stub = Stub(answer("fresh"))
    g = gateway(tmp_path, stub, cache_mode="readonly")
    assert g.call("VISION_FAST", BODY).text == "cached" and not stub.calls
    assert g.call("TEXT_SMART", BODY).text == "fresh" and len(stub.calls) == 1  # a miss calls
    assert len(list((tmp_path / "cache").rglob("*.json"))) == 1  # but stores nothing


def test_off_neither_reads_nor_writes(tmp_path: Path):
    gateway(tmp_path, Stub(answer("cached"))).call("VISION_FAST", BODY)
    stub = Stub(answer("fresh"))
    g = gateway(tmp_path, stub, cache_mode="off")
    assert g.call("VISION_FAST", BODY).text == "fresh" and len(stub.calls) == 1
    assert len(list((tmp_path / "cache").rglob("*.json"))) == 1


def test_cache_mode_and_folder_come_from_the_environment(tmp_path: Path):
    env = {**ENV, "CACHE_MODE": "readonly", "DATA_DIR": str(tmp_path / "data")}
    g = og.Gateway(env=env, transport=Stub(answer()), prices={})
    assert g.cache_mode == "readonly" and g.cache_dir == tmp_path / "data" / "cache" / "openai"
    with pytest.raises(og.GatewayError, match="CACHE_MODE must be one of"):
        og.Gateway(env={**ENV, "CACHE_MODE": "sometimes"}, transport=Stub(answer()), prices={})
    nowhere = og.Gateway(env=ENV, transport=Stub(answer()), prices={})
    with pytest.raises(og.GatewayError, match="set DATA_DIR or pass cache_dir"):
        nowhere.call("VISION_FAST", BODY)


# 15 · cost log ────────────────────────────────────────────────────────────────


def test_each_call_logs_tokens_and_cost(tmp_path: Path):
    logged: list[og.CallLog] = []
    prices = {"vision-model-a": og.Price(input=2.0, output=8.0, cached_input=0.5)}
    g = gateway(tmp_path, Stub(answer()), prices=prices, on_call=logged.append)
    result = g.call("VISION_FAST", BODY)
    # 600 fresh input x $2 + 400 cached x $0.5 + 200 output x $8, per million tokens.
    expected = (600 * 2.0 + 400 * 0.5 + 200 * 8.0) / 1_000_000
    assert result.cost_usd == pytest.approx(expected) and g.spent_usd == pytest.approx(expected)
    entry = logged[0]
    assert (entry.tier, entry.model, entry.cache_hit, entry.attempts) == (
        "VISION_FAST",
        "vision-model-a",
        False,
        1,
    )
    assert entry.usage == og.Usage(input_tokens=1000, output_tokens=200, cached_input_tokens=400)
    g.call("VISION_FAST", BODY)
    assert logged[1].cache_hit and logged[1].cost_usd == 0.0


def test_an_unknown_price_is_null_with_a_warning(tmp_path: Path, caplog):
    logged: list[og.CallLog] = []
    g = gateway(tmp_path, Stub(answer()), on_call=logged.append, cache_mode="off")
    with caplog.at_level(logging.WARNING, logger="scrubgpt_brain.openai"):
        assert g.call("VISION_FAST", BODY).cost_usd is None
        g.call("VISION_FAST", BODY)
    assert logged[0].cost_usd is None and g.spent_usd == 0.0
    warnings = [r.getMessage() for r in caplog.records if "no price" in r.getMessage()]
    assert warnings == ["no price for model vision-model-a: its cost is not counted"]


def test_prices_load_from_yaml(tmp_path: Path):
    path = tmp_path / "prices.yaml"
    path.write_text("m: {input: 1.25, output: 10}\n", encoding="utf-8")
    assert og.load_prices(path) == {"m": og.Price(input=1.25, output=10.0)}
    assert og.load_prices(tmp_path / "none.yaml") == {}
    assert og.load_prices() == {}  # the repo's list starts empty: no guessed prices
    path.write_text("m: {input: -1, output: 10}\n", encoding="utf-8")
    with pytest.raises(og.GatewayError, match="prices must be numbers >= 0"):
        og.load_prices(path)


# 16 · refusals and truncation ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (
            answer(output=[{"type": "message", "content": [{"type": "refusal", "refusal": "no"}]}]),
            og.RefusalError,
        ),
        (
            answer(status="incomplete", incomplete_details={"reason": "max_output_tokens"}),
            og.TruncatedError,
        ),
        (
            answer(status="incomplete", incomplete_details={"reason": "content_filter"}),
            og.RefusalError,
        ),
        (
            {"choices": [{"finish_reason": "length", "message": {"content": '{"st'}}]},
            og.TruncatedError,
        ),
        (
            {"choices": [{"finish_reason": "stop", "message": {"content": None, "refusal": "no"}}]},
            og.RefusalError,
        ),
        (answer(status="failed", error={"message": "server"}), og.GatewayError),
    ],
)
def test_refusals_and_truncation_raise_and_are_never_cached(tmp_path: Path, response, error):
    stub = Stub(response)
    with pytest.raises(error):
        gateway(tmp_path, stub).call("VISION_FAST", BODY)
    assert not list((tmp_path / "cache").rglob("*.json"))
    with pytest.raises(error):  # not cached: the next call asks again
        gateway(tmp_path, stub).call("VISION_FAST", BODY)
    assert len(stub.calls) == 2


def test_a_chat_completions_answer_is_read_too(tmp_path: Path):
    chat = {
        "choices": [{"finish_reason": "stop", "message": {"content": "ok"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 2},
    }
    result = gateway(tmp_path, Stub(chat)).call(
        "TEXT_SMART", {"messages": []}, endpoint="chat/completions"
    )
    assert result.text == "ok" and result.usage == og.Usage(10, 2, 0)
