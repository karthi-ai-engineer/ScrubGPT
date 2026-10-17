"""Tester 2 helpers for the App track acceptance tests (Block 1: I1).

Everything runs offline on copies of the synthetic fixtures (`contracts/fixtures`, D-026) in
`tmp_path`; the committed fixtures are never modified. Shared helpers are fixtures, because test
files can't import each other under `--import-mode=importlib`.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[4]
FIXTURES = REPO_ROOT / "contracts" / "fixtures"
FIXTURE_CASE_ID = "case-fixture-01"
FIXTURE_CASE = FIXTURES / "cases" / FIXTURE_CASE_ID
FIXTURE_REFERENCE = FIXTURES / "reference" / "rarp.json"

SETTING_VARS = ("DATA_DIR", "APP_PORT", "BRAIN_MODE", "MOCK_BRAIN_URL", "BRAIN_URL", "APP_DB_PATH")


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def fixture_case() -> Path:
    return FIXTURE_CASE


@pytest.fixture
def fixture_reference() -> Path:
    return FIXTURE_REFERENCE


@pytest.fixture(autouse=True)
def clean_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """No setting leaks in from the developer's shell; each test sets what it needs."""
    for name in SETTING_VARS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """A private copy of the fixture DATA_DIR: `cases/case-fixture-01/` + `reference/rarp.json`."""
    target = tmp_path / "data"
    (target / "cases").mkdir(parents=True)
    shutil.copytree(FIXTURE_CASE, target / "cases" / FIXTURE_CASE_ID)
    (target / "reference").mkdir()
    shutil.copy2(FIXTURE_REFERENCE, target / "reference" / "rarp.json")
    return target


def _clone_case(source: Path, target_parent: Path, new_id: str, *, video: bool = True) -> Path:
    """A copy of a case package under a new case id (ids, file names and clip names renamed)."""
    old_id = source.name
    target = target_parent / new_id
    target.mkdir(parents=True)
    for path in source.rglob("*"):
        rel = path.relative_to(source)
        out = target / Path(str(rel).replace(old_id, new_id))
        if path.is_dir():
            out.mkdir(parents=True, exist_ok=True)
            continue
        if rel.as_posix() == "video.mp4" and not video:
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == ".json":
            out.write_text(
                path.read_text(encoding="utf-8").replace(old_id, new_id),
                encoding="utf-8",
                newline="\n",
            )
        else:
            shutil.copy2(path, out)
    return target


@pytest.fixture
def clone_case() -> Callable[..., Path]:
    """`clone_case(target_parent, new_id, video=True)` copies the fixture case under a new id."""

    def make(target_parent: Path, new_id: str, *, video: bool = True) -> Path:
        return _clone_case(FIXTURE_CASE, target_parent, new_id, video=video)

    return make


@pytest.fixture
def read_json() -> Callable[[Path], object]:
    def read(path: Path) -> object:
        return json.loads(path.read_text(encoding="utf-8"))

    return read


@pytest.fixture
def write_json() -> Callable[[Path, object], None]:
    def write(path: Path, data: object) -> None:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return write


@pytest.fixture
def tree_digest() -> Callable[[Path], dict[str, str]]:
    """`{relative path: sha256}` of every file under a folder (to prove nothing was modified)."""

    def digest(root: Path) -> dict[str, str]:
        return {
            p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*"))
            if p.is_file()
        }

    return digest


@pytest.fixture
def make_settings(tmp_path: Path):
    """Settings for an in-process app: DATA_DIR given, local DB under tmp, no web dist."""
    from scrubgpt_app.settings import Settings

    def make(data: Path, *, web_dist: Path | None = None, **extra: str):
        environ = {"DATA_DIR": str(data), "APP_DB_PATH": str(tmp_path / "app.db"), **extra}
        settings = Settings.load(environ, dotenv=False)
        return dataclasses.replace(
            settings, web_dist=web_dist if web_dist is not None else tmp_path / "no-web-dist"
        )

    return make


@pytest.fixture
def make_client(make_settings) -> Iterator[Callable[..., TestClient]]:
    """`make_client(data_dir, web_dist=None)` → a TestClient on `create_app` (closed afterwards)."""
    from scrubgpt_app.api import create_app

    clients: list[TestClient] = []

    def make(data: Path, *, web_dist: Path | None = None) -> TestClient:
        client = TestClient(create_app(make_settings(data, web_dist=web_dist)))
        client.__enter__()
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture
def client(make_client, data_dir: Path) -> TestClient:
    return make_client(data_dir)


@pytest.fixture
def run_cli() -> Callable[..., tuple[int, str]]:
    """`run_cli(*args)` → (exit code, everything printed) for `scrubgpt-app` in-process."""
    from scrubgpt_app.cli import main

    def run(*args: str) -> tuple[int, str]:
        lines: list[str] = []
        try:
            code = main(list(args), out=lambda s: lines.append(str(s)))
        except SystemExit as exc:  # argparse usage errors
            code = exc.code if isinstance(exc.code, int) else 2
        return int(code), "\n".join(lines)

    return run


def _console_script() -> str:
    scripts = Path(sys.executable).parent
    found = shutil.which("scrubgpt-app", path=str(scripts))
    if found is None:
        pytest.skip("the scrubgpt-app console script is not installed next to this Python")
    return found


@pytest.fixture
def run_script() -> Callable[..., subprocess.CompletedProcess[str]]:
    """`run_script(*args, env=..., cwd=...)` runs the installed `scrubgpt-app` console script."""

    def run(*args: str, env: dict[str, str] | None = None, cwd: Path | None = None):
        environ = {k: v for k, v in os.environ.items() if k not in SETTING_VARS}
        environ.update(env or {})
        environ["PYTHONUTF8"] = "1"
        return subprocess.run(
            [_console_script(), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environ,
            cwd=str(cwd or REPO_ROOT),
            timeout=120,
        )

    return run


def _kill_tree(proc: subprocess.Popen[str]) -> None:
    """Stop a process and every child (on Windows a plain terminate can leave a child running)."""
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, check=False
        )
    else:
        proc.kill()
    proc.wait(timeout=30)


@pytest.fixture
def run_script_bounded() -> Callable[..., tuple[int | None, str]]:
    """`run_script_bounded(*args, env=..., timeout=...)` → (exit code, output) of the installed
    `scrubgpt-app` script; exit code `None` if it was still running at the timeout (it is then
    stopped with its whole process tree). For `serve`, which must not start on a bad setting."""

    def run(*args: str, env: dict[str, str] | None = None, timeout: float = 60.0):
        environ = {k: v for k, v in os.environ.items() if k not in SETTING_VARS}
        environ.update(env or {})
        environ["PYTHONUTF8"] = "1"
        proc = subprocess.Popen(
            [_console_script(), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environ,
            cwd=str(REPO_ROOT),
        )
        try:
            out, _ = proc.communicate(timeout=timeout)
            return proc.returncode, out
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            out, _ = proc.communicate()
            return None, out or ""
        finally:
            _kill_tree(proc)

    return run


# --- Block 2 (I5): a real app server on a free port, and a small SSE reader ----------------------
#
# FastAPI's in-process TestClient buffers a whole response, so an endless `text/event-stream`
# never returns through it (brief, criterion 2). These helpers run `create_app` under uvicorn in a
# background thread on 127.0.0.1:<free port> and read the stream over a real socket.


def free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@dataclasses.dataclass
class LiveServer:
    base_url: str
    host: str
    port: int
    app: object


class SSEClient:
    """One `GET /api/events` connection read line by line (no SSE library, no reconnect)."""

    def __init__(self, host: str, port: int, path: str = "/api/events", timeout: float = 10.0):
        import http.client

        self.conn = http.client.HTTPConnection(host, port, timeout=timeout)
        self.conn.request("GET", path, headers={"Accept": "text/event-stream"})
        self.response = self.conn.getresponse()
        self.status = self.response.status
        self.headers = {k.lower(): v for k, v in self.response.getheaders()}
        self.lines: list[str] = []
        self._pending: list[str] = []
        self.closed = False

    def read_line(self) -> str:
        raw = self.response.readline()
        if raw == b"":
            self.closed = True
            raise EOFError("the event stream ended")
        line = raw.decode("utf-8").rstrip("\r\n")
        self.lines.append(line)
        return line

    def read_block(self) -> list[str]:
        """The lines of the next block (up to the blank line that ends it)."""
        block: list[str] = []
        while True:
            line = self.read_line()
            if line == "":
                if block:
                    return block
                continue
            block.append(line)

    def next_event(self, deadline_s: float = 10.0) -> dict[str, object]:
        """The next block with an `event:` field, skipping comment-only blocks."""
        import time

        end = time.monotonic() + deadline_s
        while time.monotonic() < end:
            block = self.read_block()
            if all(line.startswith(":") for line in block):
                continue
            return parse_block(block)
        raise TimeoutError("no event within the deadline")

    def close(self) -> None:
        try:
            self.response.close()
        finally:
            self.conn.close()


def parse_block(block: list[str]) -> dict[str, object]:
    """`{"lines": [...], "id": ..., "event": ..., "data": [...], "fields": [field names]}`."""
    fields: list[str] = []
    out: dict[str, object] = {"lines": block, "data": []}
    for line in block:
        if line.startswith(":"):
            continue
        name, _, value = line.partition(":")
        value = value[1:] if value.startswith(" ") else value
        fields.append(name)
        if name == "data":
            out["data"].append(value)  # type: ignore[union-attr]
        else:
            out[name] = value
    out["fields"] = fields
    return out


@pytest.fixture
def live_server(make_settings) -> Iterator[Callable[..., LiveServer]]:
    """`live_server(data_dir, heartbeat_s=0.2)` → a running uvicorn server on a free port."""
    import threading
    import time

    import uvicorn
    from scrubgpt_app.api import create_app

    running: list[tuple[uvicorn.Server, threading.Thread]] = []

    def start(data: Path, *, heartbeat_s: float = 0.2) -> LiveServer:
        app = create_app(make_settings(data), heartbeat_s=heartbeat_s)
        port = free_port()
        config = uvicorn.Config(
            app, host="127.0.0.1", port=port, log_level="warning", timeout_graceful_shutdown=1
        )
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        running.append((server, thread))
        end = time.monotonic() + 20
        while not server.started:
            if time.monotonic() > end or not thread.is_alive():
                raise RuntimeError("the app server did not start")
            time.sleep(0.02)
        return LiveServer(f"http://127.0.0.1:{port}", "127.0.0.1", port, app)

    yield start
    for server, thread in running:
        server.should_exit = True
        thread.join(timeout=10)
        if thread.is_alive():
            server.force_exit = True
            thread.join(timeout=5)


@pytest.fixture
def sse_connect() -> Iterator[Callable[..., SSEClient]]:
    """`sse_connect(server)` opens `GET /api/events`; every client is closed afterwards."""
    clients: list[SSEClient] = []

    def connect(server: LiveServer, path: str = "/api/events") -> SSEClient:
        client = SSEClient(server.host, server.port, path)
        clients.append(client)
        return client

    yield connect
    for client in clients:
        try:
            client.close()
        except OSError:
            pass


@pytest.fixture
def http_post() -> Callable[..., tuple[int, object]]:
    """`http_post(base_url, path)` → (status, parsed JSON body) over a real socket."""
    import httpx

    def post(base_url: str, path: str) -> tuple[int, object]:
        response = httpx.post(base_url + path, timeout=10)
        try:
            body: object = response.json()
        except ValueError:
            body = response.text
        return response.status_code, body

    return post


@pytest.fixture
def start_serve(tmp_path: Path) -> Iterator[Callable[..., tuple[str, int]]]:
    """`start_serve(data_dir)` runs the installed `scrubgpt-app serve --port <free>`; returns
    (base URL, port) once `/api/health` answers. Stopped with its whole process tree."""
    import time

    import httpx

    procs: list[subprocess.Popen[str]] = []

    def start(data: Path) -> tuple[str, int]:
        port = free_port()
        environ = {k: v for k, v in os.environ.items() if k not in SETTING_VARS}
        environ.update(
            {
                "DATA_DIR": str(data),
                "APP_DB_PATH": str(tmp_path / "serve.db"),
                "BRAIN_MODE": "mock",
                "PYTHONUTF8": "1",
            }
        )
        proc = subprocess.Popen(
            [_console_script(), "serve", "--port", str(port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            env=environ,
            cwd=str(REPO_ROOT),
        )
        procs.append(proc)
        base = f"http://127.0.0.1:{port}"
        end = time.monotonic() + 60
        while time.monotonic() < end:
            if proc.poll() is not None:
                raise RuntimeError(f"scrubgpt-app serve exited with {proc.returncode}")
            try:
                if httpx.get(base + "/api/health", timeout=2).status_code == 200:
                    return base, port
            except httpx.HTTPError:
                pass
            time.sleep(0.2)
        raise RuntimeError("scrubgpt-app serve did not answer /api/health")

    yield start
    for proc in procs:
        _kill_tree(proc)
