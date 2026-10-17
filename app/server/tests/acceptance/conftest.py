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
