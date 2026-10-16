"""Tester 2 (T2) shared fixtures for the Phase 0 acceptance tests of Dev2's contract files.

Spec sources: issue #5 (Team Lead triage, criteria 1-11), plan §4.1/§4.3/§4.4/§4.5,
D-023, D-034, D-036, D-037, D-048, contracts/brain_api.md. Offline only: synthetic fixtures and
the fake Brain (in-process through its ASGI app, or as a subprocess for the CLI criteria).
"""

from __future__ import annotations

import copy
import json
import math
import os
import re
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import uuid6
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[4]
CONTRACTS = REPO / "contracts"
FIXTURES = CONTRACTS / "fixtures"
BRAIN_API_FIXTURES = FIXTURES / "brain_api"
CASE_DIR = FIXTURES / "cases" / "case-fixture-01"
REFERENCE = FIXTURES / "reference" / "rarp.json"

POST_ENDPOINTS = ("transcribe", "extract", "translate", "embed", "ask", "briefing")
ALL_ENDPOINTS = ("health", *POST_ENDPOINTS)
MAX_AUDIO_BYTES = 25 * 1024 * 1024  # brain_api.md: 26 214 400 bytes; plan §4.4 "max 25 MB"


@pytest.fixture(scope="session")
def paths() -> dict[str, Path]:
    return {
        "repo": REPO,
        "contracts": CONTRACTS,
        "fixtures": FIXTURES,
        "brain_api": BRAIN_API_FIXTURES,
        "case_dir": CASE_DIR,
        "reference": REFERENCE,
    }


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def read_json() -> Callable[[Path], Any]:
    return _read_json


@pytest.fixture(scope="session")
def endpoints():
    from scrubgpt_contracts.models.brain_api import ENDPOINTS

    return ENDPOINTS


@pytest.fixture(scope="session")
def request_fixture() -> Callable[[str], Any]:
    """`<name>.request.json` as a fresh dict each call (D-037)."""

    def load(name: str) -> Any:
        return _read_json(BRAIN_API_FIXTURES / f"{name}.request.json")

    return load


@pytest.fixture(scope="session")
def audio_fixture() -> Path:
    found = sorted(BRAIN_API_FIXTURES.glob("transcribe.request.audio.*"))
    assert len(found) == 1, f"expected exactly one transcribe.request.audio.<ext>, found {found}"
    return found[0]


@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:
    """The fake Brain in-process (`scrubgpt_contracts.mock_brain.app.create_app`)."""
    from scrubgpt_contracts.mock_brain.app import create_app

    with TestClient(create_app(), raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(scope="session")
def new_uuid7() -> Callable[[], str]:
    return lambda: str(uuid6.uuid7())


# --- fixture case data -----------------------------------------------------------------------


@pytest.fixture(scope="session")
def case_data() -> dict[str, Any]:
    case = _read_json(CASE_DIR / "case.json")
    moments = {m["id"]: m for m in _read_json(CASE_DIR / "moments.json")["moments"]}
    questions_file = _read_json(CASE_DIR / "questions.json")
    questions = {q["id"]: q for q in questions_file["operating"] + questions_file["reviewer"]}
    reference = _read_json(REFERENCE)
    steps = {s["id"]: s for phase in reference["phases"] for s in phase["steps"]}
    seeds = _read_json(CASE_DIR / "seed_records.json")["records"]
    return {
        "case": case,
        "moments": moments,
        "questions": questions,
        "steps": steps,
        "seeds": seeds,
        "reference": reference,
    }


@pytest.fixture(scope="session")
def build_extract(case_data, new_uuid7) -> Callable[..., dict[str, Any]]:
    """Build a full /extract request (plan §4.4) for a fixture question id."""

    def build(
        question_id: str,
        *,
        role: str = "operating_surgeon",
        mode: str = "text",
        text: str | None = "I held the camera still and waited.",
        lang: str = "en",
        tap: dict[str, Any] | None = None,
        answer_id: str | None = None,
    ) -> dict[str, Any]:
        question = copy.deepcopy(case_data["questions"][question_id])
        moment = copy.deepcopy(case_data["moments"][question["moment_id"]])
        return {
            "question": question,
            "moment": moment,
            "case_context": {
                "case": copy.deepcopy(case_data["case"]),
                "step": copy.deepcopy(case_data["steps"][moment["step_id"]]),
            },
            "answer": {
                "answer_id": answer_id or new_uuid7(),
                "mode": mode,
                "tap": tap,
                "text": text,
                "lang": lang,
                "audio_uri": None,
            },
            "answerer_role": role,
        }

    return build


# --- generic helpers -------------------------------------------------------------------------

_PATH_TOKEN = re.compile(r"([a-z_][a-z0-9_]*)|\[([0-9]+)\]")
_MISSING = object()


def _get_path(data: Any, path: str) -> Any:
    """Resolve a field path `a.b[0].c` (plan §4.1). Returns `MISSING` if it doesn't exist."""
    node = data
    for part in path.split("."):
        for name, index in _PATH_TOKEN.findall(part):
            if name:
                if not isinstance(node, dict) or name not in node:
                    return _MISSING
                node = node[name]
            else:
                i = int(index)
                if not isinstance(node, list) or i >= len(node):
                    return _MISSING
                node = node[i]
    return node


@pytest.fixture(scope="session")
def get_path() -> Callable[[Any, str], Any]:
    return _get_path


@pytest.fixture(scope="session")
def MISSING() -> object:  # noqa: N802
    return _MISSING


@pytest.fixture(scope="session")
def cosine() -> Callable[[list[float], list[float]], float]:
    def cos(a: list[float], b: list[float]) -> float:
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(x * x for x in b))
        if na == 0 or nb == 0:
            return 0.0
        return sum(x * y for x, y in zip(a, b, strict=True)) / (na * nb)

    return cos


@pytest.fixture(scope="session")
def assert_api_error() -> Callable[[httpx.Response, int, str], dict[str, Any]]:
    """Every non-200 body is an ApiError with contract_version (plan §4.1, D-034)."""
    from scrubgpt_contracts.models.common import ApiError

    def check(response: httpx.Response, status: int, code: str) -> dict[str, Any]:
        assert response.status_code == status, (response.status_code, response.text[:500])
        body = response.json()
        ApiError.model_validate(body)
        assert body["contract_version"] == "1.0"
        assert body["error"]["code"] == code
        assert isinstance(body["error"]["message"], str) and body["error"]["message"]
        assert isinstance(body["error"]["retryable"], bool)
        return body

    return check


# --- the fake Brain as a real process (criteria 7, 8) -----------------------------------------


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _script(name: str) -> Path:
    folder = Path(sys.executable).parent
    for candidate in (folder / f"{name}.exe", folder / name):
        if candidate.exists():
            return candidate
    pytest.fail(f"console script {name} not found next to {sys.executable}")


@pytest.fixture(scope="session")
def console_script() -> Callable[[str], Path]:
    return _script


def _kill_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
            capture_output=True,
            check=False,
        )
    else:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)


@pytest.fixture(scope="module")
def mock_brain_url(tmp_path_factory) -> Iterator[str]:
    """`scrubgpt-mock-brain --port <free>` started through its console script."""
    port = _free_port()
    log = tmp_path_factory.mktemp("mock_brain") / "server.log"
    kwargs: dict[str, Any] = {}
    if os.name != "nt":
        kwargs["start_new_session"] = True
    with log.open("wb") as out:
        proc = subprocess.Popen(
            [str(_script("scrubgpt-mock-brain")), "--port", str(port)],
            stdout=out,
            stderr=subprocess.STDOUT,
            cwd=REPO,
            **kwargs,
        )
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 60
        while True:
            if proc.poll() is not None:
                pytest.fail(f"scrubgpt-mock-brain exited early:\n{log.read_text(errors='replace')}")
            try:
                if httpx.get(f"{base}/health", timeout=2).status_code:
                    break
            except httpx.HTTPError:
                pass
            if time.monotonic() > deadline:
                pytest.fail(
                    f"scrubgpt-mock-brain did not start:\n{log.read_text(errors='replace')}"
                )
            time.sleep(0.3)
        yield base
    finally:
        _kill_tree(proc)
