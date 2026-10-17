"""I1 acceptance: `scrubgpt-app serve`, the documented run command (brief criteria 2 and 3).

Sources: app/server/README.md Usage (`uv run scrubgpt-app serve` → http://127.0.0.1:8000
(APP_PORT), DATA_DIR from the settings; `--data-dir` overrides DATA_DIR for one run), the API
table (`GET /api/health`). Runs on a free local port and stops the whole process tree afterwards.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _kill_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, check=False
        )
    else:
        proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=15)


def _health(port: int, deadline_s: float = 45.0) -> dict:
    url = f"http://127.0.0.1:{port}/api/health"
    end = time.monotonic() + deadline_s
    last: Exception | None = None
    while time.monotonic() < end:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:  # noqa: S310 (localhost)
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, ConnectionError, OSError) as exc:
            last = exc
            time.sleep(0.3)
    raise AssertionError(f"the server on :{port} never answered /api/health: {last}")


@pytest.fixture
def serve(tmp_path: Path):
    procs: list[subprocess.Popen] = []
    logs: list = []

    def start(*args: str, env: dict[str, str]) -> subprocess.Popen:
        script = Path(sys.executable).parent / (
            "scrubgpt-app.exe" if sys.platform == "win32" else "scrubgpt-app"
        )
        if not script.exists():
            pytest.skip("the scrubgpt-app console script is not installed next to this Python")
        environ = {
            k: v
            for k, v in os.environ.items()
            if k not in {"DATA_DIR", "APP_PORT", "BRAIN_MODE", "APP_DB_PATH"}
        }
        environ.update(env)
        environ.setdefault("APP_DB_PATH", str(tmp_path / "app.db"))
        log = open(tmp_path / f"serve-{len(procs)}.log", "wb")  # noqa: SIM115
        proc = subprocess.Popen(
            [str(script), "serve", *args], env=environ, stdout=log, stderr=subprocess.STDOUT
        )
        procs.append(proc)
        logs.append(log)
        return proc

    yield start
    for proc in procs:
        _kill_tree(proc)
    for log in logs:
        log.close()


def test_serve_uses_app_port_and_data_dir(serve, data_dir: Path) -> None:
    """README: `serve` listens on APP_PORT and loads DATA_DIR; /api/health reports it."""
    port = _free_port()
    serve(env={"APP_PORT": str(port), "DATA_DIR": str(data_dir)})
    body = _health(port)
    assert body["cases"] == {"loaded": 1, "rejected": 0}
    assert body["brain_mode"] == "mock"


def test_serve_options_override_settings(serve, data_dir: Path, tmp_path: Path) -> None:
    """README: `--port` overrides APP_PORT and `--data-dir` overrides DATA_DIR for one run."""
    port = _free_port()
    serve(
        "--port",
        str(port),
        "--data-dir",
        str(data_dir),
        env={"APP_PORT": "1", "DATA_DIR": str(tmp_path / "missing")},
    )
    assert _health(port)["cases"]["loaded"] == 1
