"""AC17 (no longer BLOCKED) and #7 AC6 for `live`: `scrubgpt-validate live --base-url <url>`
against Dev2's real fake Brain (`scrubgpt-mock-brain`) and real `ENDPOINTS` registry (plan §4.5,
D-037; #5 registry shape; D-052 exit codes, refined by the Team Lead's newest #7 ruling, D-055).

The fake Brain is started on a free port on 127.0.0.1 inside these tests and stopped at the end
of the module. To see what `live` actually sends, some tests put a small recording proxy (also on
127.0.0.1) between `live` and the fake Brain; the proxy can also tamper with one response to
check that `live` notices. The D-055 tests also use small stubs on 127.0.0.1 (one that answers
every request the same way, one that accepts connections and never answers). Nothing leaves the
machine and nothing calls OpenAI.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from scrubgpt_contracts.models.brain_api import ENDPOINTS

FIXTURES_BRAIN_API = Path(__file__).resolve().parents[3] / "fixtures" / "brain_api"
POST_NAMES = [name for name, ep in ENDPOINTS.items() if ep.method == "POST"]


# --- the fake Brain, started and stopped here --------------------------------------------------


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _command(script: str) -> list[str]:
    """`uv run <script>` (without touching uv.lock or the venv), else the installed script."""
    uv = shutil.which("uv")
    if uv:
        return [uv, "run", "--frozen", "--no-sync", script]
    exe = shutil.which(script)
    assert exe, f"{script} is not installed"
    return [exe]


def _stop(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, check=False
        )
    else:
        os.killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        if sys.platform != "win32":
            os.killpg(proc.pid, signal.SIGKILL)
        proc.kill()
        proc.wait(timeout=10)


@dataclass
class FakeBrain:
    url: str
    port: int
    proc: subprocess.Popen


@pytest.fixture(scope="module")
def fake_brain(tmp_path_factory) -> Iterator[FakeBrain]:
    """`uv run scrubgpt-mock-brain --port <free port>`; waits for `/health`; stops it after."""
    port = _free_port()
    log = tmp_path_factory.mktemp("fake-brain") / "fake-brain.log"
    repo = Path(__file__).resolve().parents[4]
    with log.open("wb") as sink:
        proc = subprocess.Popen(
            [*_command("scrubgpt-mock-brain"), "--port", str(port), "--host", "127.0.0.1"],
            cwd=repo,
            stdout=sink,
            stderr=subprocess.STDOUT,
            start_new_session=sys.platform != "win32",
        )
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 90
        while True:
            if proc.poll() is not None:
                pytest.fail(f"fake Brain exited early:\n{log.read_text(errors='replace')}")
            try:
                with urllib.request.urlopen(url + "/health", timeout=2) as resp:
                    if resp.status == 200:
                        break
            except (urllib.error.URLError, OSError):
                pass
            if time.monotonic() > deadline:
                pytest.fail(f"fake Brain not up after 90 s:\n{log.read_text(errors='replace')}")
            time.sleep(0.3)
        yield FakeBrain(url=url, port=port, proc=proc)
    finally:
        _stop(proc)
        deadline = time.monotonic() + 15
        while _port_open(port) and time.monotonic() < deadline:
            time.sleep(0.3)
        assert not _port_open(port), "the fake Brain is still listening after the tests"


# --- a recording (and optionally tampering) proxy -------------------------------------------


@dataclass
class Exchange:
    method: str
    path: str
    request_body: bytes
    request_type: str
    status: int
    response: Any


Tamper = Callable[[Exchange], tuple[int, Any] | None]


@dataclass
class Proxy:
    url: str
    log: list[Exchange] = field(default_factory=list)
    tamper: Tamper | None = None

    def exchanges(self, method: str, path: str) -> list[Exchange]:
        return [x for x in self.log if x.method == method and x.path == path]


def _read_body(handler: BaseHTTPRequestHandler) -> bytes:
    if handler.headers.get("Transfer-Encoding", "").lower() == "chunked":
        chunks = []
        while True:
            size = int(handler.rfile.readline().split(b";")[0].strip() or b"0", 16)
            if size == 0:
                handler.rfile.readline()
                break
            chunks.append(handler.rfile.read(size))
            handler.rfile.readline()
        return b"".join(chunks)
    length = int(handler.headers.get("Content-Length") or 0)
    return handler.rfile.read(length) if length else b""


def _handler_for(upstream: str, proxy: Proxy):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _forward(self, method: str) -> None:
            body = _read_body(self)
            ctype = self.headers.get("Content-Type", "")
            headers = {"Content-Type": ctype} if ctype else {}
            req = urllib.request.Request(
                upstream + self.path,
                data=body if method == "POST" else None,
                headers=headers,
                method=method,
            )
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    status, data = resp.status, resp.read()
            except urllib.error.HTTPError as exc:
                status, data = exc.code, exc.read()
            try:
                parsed: Any = json.loads(data)
            except ValueError:
                parsed = data
            exchange = Exchange(method, self.path, body, ctype, status, parsed)
            proxy.log.append(exchange)
            if proxy.tamper is not None:
                changed = proxy.tamper(exchange)
                if changed is not None:
                    status, parsed = changed
            out = (
                parsed
                if isinstance(parsed, bytes)
                else json.dumps(parsed, ensure_ascii=False).encode("utf-8")
            )
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        def do_GET(self):
            self._forward("GET")

        def do_POST(self):
            self._forward("POST")

    return Handler


@pytest.fixture
def proxy(fake_brain) -> Iterator[Proxy]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), None)  # handler set below
    p = Proxy(url=f"http://127.0.0.1:{server.server_address[1]}")
    server.RequestHandlerClass = _handler_for(fake_brain.url, p)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield p
    finally:
        server.shutdown()
        server.server_close()


def _live(run_validate, url: str, *extra: str | Path):
    return run_validate("live", "--base-url", url, "--timeout", "60", *extra)


def _is_bad_request(x: Exchange) -> bool:
    body = x.response
    return (
        x.status == 400
        and isinstance(body, dict)
        and body.get("contract_version") == "1.0"
        and isinstance(body.get("error"), dict)
        and body["error"].get("code") == "bad_request"
    )


def _is_empty_request(x: Exchange) -> bool:
    body = x.request_body.strip()
    if body in (b"", b"{}", b"null"):
        return True
    if "multipart/form-data" in x.request_type:
        return b'name="' not in body
    return False


# --- AC17: exit 0 against the real fake Brain --------------------------------------------------


def test_ac17_registry_is_the_real_one():
    """AC17 precondition: Dev2's real `ENDPOINTS` exists (it was missing when AC17 was BLOCKED)
    and has GET and POST entries with the #5 shape."""
    assert ENDPOINTS
    for name, ep in ENDPOINTS.items():
        assert ep.method in ("GET", "POST"), name
        assert ep.path.startswith("/"), name
        assert ep.response is not None, name
        assert isinstance(ep.files, tuple), name
    assert POST_NAMES


def test_ac17_live_against_the_fake_brain_exits_0(fake_brain, run_validate):
    """AC17: "`uv run scrubgpt-validate live --base-url http://127.0.0.1:<port>` exits 0" against
    `uv run scrubgpt-mock-brain --port <free port>` (in-process `main`)."""
    result = _live(run_validate, fake_brain.url)
    assert result.code == 0, result.output


def test_ac17_live_console_script_against_the_fake_brain_exits_0(fake_brain, paths):
    """AC17, literally: `uv run scrubgpt-validate live --base-url http://127.0.0.1:<port>` (no
    other option) exits 0."""
    proc = subprocess.run(
        [*_command("scrubgpt-validate"), "live", "--base-url", fake_brain.url],
        cwd=paths["repo"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_ac17_live_checks_every_endpoint_and_probe(proxy, run_validate):
    """AC17: "checks every `ENDPOINTS` entry plus the empty-request probe for each POST endpoint"
    (D-037; §4.1: an empty POST gets HTTP 400 `ApiError` `bad_request`)."""
    result = _live(run_validate, proxy.url)
    assert result.code == 0, result.output
    for name, ep in ENDPOINTS.items():
        calls = proxy.exchanges(ep.method, ep.path)
        assert any(x.status == 200 for x in calls), f"{name}: no successful call\n{result.output}"
        if ep.method == "POST":
            probes = [x for x in calls if _is_empty_request(x)]
            assert probes, f"{name}: no empty-request probe was sent"
            assert all(_is_bad_request(x) for x in probes), f"{name}: probe not 400 bad_request"
    unknown = {(x.method, x.path) for x in proxy.log} - {
        (ep.method, ep.path) for ep in ENDPOINTS.values()
    }
    assert not unknown, f"calls outside the registry: {unknown}"


def test_ac17_live_sends_the_request_fixtures(proxy, run_validate):
    """AC17 / plan §4.5: `live` "sends every request fixture in the ENDPOINTS registry": each
    JSON POST endpoint gets its `<name>.request.json`; multipart endpoints get their files."""
    assert _live(run_validate, proxy.url).code == 0
    for name in POST_NAMES:
        ep = ENDPOINTS[name]
        fixture = json.loads((FIXTURES_BRAIN_API / f"{name}.request.json").read_text("utf-8"))
        calls = [x for x in proxy.exchanges("POST", ep.path) if x.status == 200]
        if ep.files:
            assert all("multipart/form-data" in x.request_type for x in calls), name
            for file_field in ep.files:
                assert any(f'name="{file_field}"'.encode() in x.request_body for x in calls), name
        else:
            assert any(json.loads(x.request_body) == fixture for x in calls), name


# --- AC17: `live` notices a non-conforming Brain (real registry, real fake Brain) --------------


@pytest.mark.parametrize("name", list(ENDPOINTS))
def test_ac17_live_fails_when_an_endpoint_drops_contract_version(proxy, run_validate, name):
    """AC17 + plan §4.1 ("every API response carries contract_version"): the proxy removes
    `contract_version` from one endpoint's 200 response -> exit 1 naming that endpoint. Shows
    that every ENDPOINTS entry's response is really checked."""
    ep = ENDPOINTS[name]

    def tamper(x: Exchange):
        if (x.method, x.path) == (ep.method, ep.path) and x.status == 200:
            body = dict(x.response)
            body.pop("contract_version", None)
            return 200, body
        return None

    proxy.tamper = tamper
    result = _live(run_validate, proxy.url)
    assert result.code == 1, result.output
    assert name in result.problems, result.output


@pytest.mark.parametrize("name", POST_NAMES)
def test_ac17_live_fails_when_a_probe_is_not_400_bad_request(proxy, run_validate, name):
    """AC17: the empty-request probe must get HTTP 400 `bad_request` (§4.1, FastAPI's 422 is
    mapped to 400): the proxy turns one endpoint's probe answer into a raw FastAPI 422 -> exit
    1 naming that endpoint."""
    ep = ENDPOINTS[name]

    def tamper(x: Exchange):
        if x.path == ep.path and _is_empty_request(x):
            return 422, {"detail": [{"loc": ["body"], "msg": "Field required", "type": "missing"}]}
        return None

    proxy.tamper = tamper
    result = _live(run_validate, proxy.url)
    assert result.code == 1, result.output
    assert name in result.problems, result.output


def test_ac17_live_fails_on_a_half_empty_bilingual(proxy, run_validate):
    """AC17 + §4.1 (Bilingual: both halves non-empty): `/v1/translate` answering an empty `en`
    -> exit 1 naming translate."""
    ep = ENDPOINTS["translate"]

    def tamper(x: Exchange):
        if x.path == ep.path and x.status == 200:
            return 200, {"contract_version": "1.0", "items": [{"ja": "出血", "en": ""}]}
        return None

    proxy.tamper = tamper
    result = _live(run_validate, proxy.url)
    assert result.code == 1, result.output
    assert "translate" in result.problems, result.output


# --- #7 AC6 for `live`: missing input -> 2, and 2 wins over 1 ---------------------------------


@pytest.fixture
def fixtures_copy(tmp_path) -> Path:
    target = tmp_path / "brain_api"
    shutil.copytree(FIXTURES_BRAIN_API, target)
    return target


def test_7ac6_live_with_a_copy_of_the_fixtures_exits_0(fake_brain, fixtures_copy, run_validate):
    """Control for the tests below: `--fixtures <copy>` behaves like the default."""
    result = _live(run_validate, fake_brain.url, "--fixtures", fixtures_copy)
    assert result.code == 0, result.output


def test_7ac6_live_missing_fixtures_folder_exits_2(fake_brain, tmp_path, run_validate):
    """#7 AC6: "Missing file ... -> 2" (D-052: "2 = the run could not complete (... missing
    ... input)"): `--fixtures` names a folder that doesn't exist."""
    result = _live(run_validate, fake_brain.url, "--fixtures", tmp_path / "no-such-folder")
    assert result.code == 2, result.output


def test_7ac6_live_missing_request_fixture_exits_2(fake_brain, fixtures_copy, run_validate):
    """#7 AC6: "Missing file ... -> 2": one request fixture (`translate.request.json`) is
    missing, so that endpoint can't be checked and the run can't complete."""
    (fixtures_copy / "translate.request.json").unlink()
    result = _live(run_validate, fake_brain.url, "--fixtures", fixtures_copy)
    assert result.code == 2, result.output
    assert "translate" in result.problems, result.output


def test_7ac6_live_missing_input_and_a_failure_exits_2_and_prints_it(
    proxy, fixtures_copy, run_validate
):
    """#7 point 4: "Exit 2 wins over 1" and "the checks that could run are still printed": a
    missing request fixture (2) plus an `ask` response without `contract_version` (1) -> exit 2,
    and the `ask` error is printed."""
    (fixtures_copy / "translate.request.json").unlink()
    ask = ENDPOINTS["ask"]

    def tamper(x: Exchange):
        if x.path == ask.path and x.status == 200:
            body = dict(x.response)
            body.pop("contract_version", None)
            return 200, body
        return None

    proxy.tamper = tamper
    result = _live(run_validate, proxy.url, "--fixtures", fixtures_copy)
    assert result.code == 2, result.output
    assert any("ask" in ln for ln in result.problems.splitlines()), result.output


@pytest.mark.parametrize("timeout", ["5", "0.5"])
def test_d055_ac1_live_closed_port_exits_2(run_validate, timeout):
    """D-055 AC1 (#7, Team Lead's newest ruling): "`live` against a closed port (nothing
    listening) -> exit 2" ("Exit 2: connection refused, a connect timeout or a DNS failure").
    Tightened from the earlier "never exit 0". With a short `--timeout` Windows may report the
    refused connection as a connect timeout, which is exit 2 as well."""
    port = _free_port()
    assert not _port_open(port)
    result = run_validate("live", "--base-url", f"http://127.0.0.1:{port}", "--timeout", timeout)
    assert result.code == 2, result.output


# --- D-055 AC2: the Brain answered, but badly -> exit 1 ---------------------------------------


def _stub_handler(status: int, body: bytes, content_type: str):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _answer(self) -> None:
            _read_body(self)
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self._answer()

        def do_POST(self):
            self._answer()

    return Handler


@contextlib.contextmanager
def _stub(status: int, body: bytes, content_type: str) -> Iterator[str]:
    """A Brain stand-in on 127.0.0.1 that answers every request with the same status and body."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _stub_handler(status, body, content_type))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def _api_error(code: str, retryable: bool) -> bytes:
    body = {
        "contract_version": "1.0",
        "error": {"code": code, "message": "stub error", "retryable": retryable},
    }
    return json.dumps(body).encode("utf-8")


ERROR_STATUS_STUBS = {
    "500-api-error": (500, _api_error("upstream_error", True), "application/json"),
    "503-unavailable": (503, _api_error("unavailable", True), "application/json"),
    "504-timeout": (504, _api_error("timeout", True), "application/json"),
    "503-plain-text": (503, b"Service Unavailable", "text/plain"),
    "404-not-found": (404, b'{"detail": "Not Found"}', "application/json"),
}

BAD_BODY_STUBS = {
    "version-only": (200, b'{"contract_version": "1.0"}', "application/json"),
    "empty-object": (200, b"{}", "application/json"),
    "not-json": (200, b"<html><body>ok</body></html>", "text/html"),
}


@pytest.mark.parametrize("kind", list(ERROR_STATUS_STUBS))
def test_d055_ac2_live_stub_with_an_http_error_status_exits_1(run_validate, kind):
    """D-055 AC2: "`live` against a local stub that answers with an HTTP error status ... ->
    exit 1" ("the Brain answers with an error status ... These are failed checks on the Brain
    under test"). Includes a well-formed `ApiError` `unavailable` / `timeout` answer: the Brain
    was reached, so it is still 1, not 2."""
    with _stub(*ERROR_STATUS_STUBS[kind]) as url:
        result = run_validate("live", "--base-url", url, "--timeout", "10")
    assert result.code == 1, result.output


@pytest.mark.parametrize("kind", list(BAD_BODY_STUBS))
def test_d055_ac2_live_stub_with_a_body_that_fails_the_model_exits_1(run_validate, kind):
    """D-055 AC2: "`live` against a local stub that answers ... with a body that fails the model
    -> exit 1"."""
    with _stub(*BAD_BODY_STUBS[kind]) as url:
        result = run_validate("live", "--base-url", url, "--timeout", "10")
    assert result.code == 1, result.output


@pytest.mark.parametrize("name", list(ENDPOINTS))
def test_d055_ac2_live_one_endpoint_answers_an_error_status_exits_1(proxy, run_validate, name):
    """D-055 AC2 ("answers with an HTTP error status -> exit 1"), one endpoint at a time: the
    proxy turns that endpoint's normal (fixture) answer into HTTP 503 `ApiError` `unavailable`;
    every other endpoint answers correctly -> exit 1 naming that endpoint."""
    ep = ENDPOINTS[name]

    def tamper(x: Exchange):
        if (x.method, x.path) == (ep.method, ep.path) and x.status == 200:
            return 503, json.loads(_api_error("unavailable", True))
        return None

    proxy.tamper = tamper
    result = _live(run_validate, proxy.url)
    assert result.code == 1, result.output
    assert name in result.problems, result.output


@contextlib.contextmanager
def _silent_stub() -> Iterator[tuple[str, list[socket.socket]]]:
    """Accepts TCP connections on 127.0.0.1 and never answers (nor reads)."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(64)
    server.settimeout(0.2)
    accepted: list[socket.socket] = []
    stop = threading.Event()

    def loop() -> None:
        while not stop.is_set():
            try:
                conn, _ = server.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            accepted.append(conn)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.getsockname()[1]}", accepted
    finally:
        stop.set()
        thread.join(timeout=5)
        for conn in accepted:
            conn.close()
        server.close()


def test_d055_ac2_live_stub_that_never_answers_exits_1(paths):
    """D-055 AC2: "A stub that accepts the connection but never answers, with a short read
    timeout -> exit 1" ("a read timeout after connecting" is a failed check, not an unreachable
    Brain). Runs the console script in a subprocess so a `--timeout` that isn't honoured fails
    the test instead of hanging the suite."""
    with _silent_stub() as (url, accepted):
        try:
            proc = subprocess.run(
                [*_command("scrubgpt-validate"), "live", "--base-url", url, "--timeout", "1"],
                cwd=paths["repo"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            pytest.fail("`live --timeout 1` against a silent Brain did not finish in 300 s")
        assert accepted, "live never connected to the stub"
    assert proc.returncode == 1, proc.stdout + proc.stderr
