"""I1 acceptance: settings precedence and path resolution (brief criterion 2).

Sources: app/server/README.md ("Settings come from the environment, then the repo-root `.env`,
then defaults: DATA_DIR (default ./contracts/fixtures, D-026), APP_PORT (8000), BRAIN_MODE (mock)
… Relative paths start at the repo root. `--data-dir` overrides DATA_DIR for one run"), plan §4.1
"Paths in .env" and D-034 (relative paths resolve against the repo root, not the working
directory), app/server/CLAUDE.md rule 1 (BRAIN_MODE is `mock` or `real`).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scrubgpt_app.settings import Settings


def _write_dotenv(root: Path, **values: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    text = "".join(f"{k}={v}\n" for k, v in values.items())
    (root / ".env").write_text(text, encoding="utf-8")


def test_defaults(repo_root: Path) -> None:
    """Criterion 2 (README): defaults are DATA_DIR ./contracts/fixtures (repo root), APP_PORT
    8000, BRAIN_MODE mock."""
    settings = Settings.load({}, dotenv=False)
    assert settings.data_dir == (repo_root / "contracts" / "fixtures").resolve()
    assert settings.port == 8000
    assert str(settings.brain_mode) == "mock"


def test_dotenv_wins_over_defaults(tmp_path: Path) -> None:
    """Criterion 2: the repo-root `.env` wins over the defaults."""
    root = tmp_path / "root"
    data = tmp_path / "dotenv-data"
    _write_dotenv(root, DATA_DIR=str(data), APP_PORT="8123", BRAIN_MODE="real")
    settings = Settings.load({}, root=root)
    assert settings.data_dir == data.resolve()
    assert settings.port == 8123
    assert str(settings.brain_mode) == "real"


def test_environment_wins_over_dotenv(tmp_path: Path) -> None:
    """Criterion 2: environment variables win over the repo-root `.env`."""
    root = tmp_path / "root"
    _write_dotenv(root, DATA_DIR=str(tmp_path / "dotenv-data"), APP_PORT="8123", BRAIN_MODE="real")
    env_data = tmp_path / "env-data"
    settings = Settings.load(
        {"DATA_DIR": str(env_data), "APP_PORT": "9001", "BRAIN_MODE": "mock"}, root=root
    )
    assert settings.data_dir == env_data.resolve()
    assert settings.port == 9001
    assert str(settings.brain_mode) == "mock"


def test_environment_wins_over_dotenv_from_os_environ(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Criterion 2 with the real process environment (no explicit mapping)."""
    root = tmp_path / "root"
    _write_dotenv(root, APP_PORT="8123")
    monkeypatch.setenv("APP_PORT", "9002")
    assert Settings.load(root=root).port == 9002


def test_relative_paths_resolve_against_repo_root_not_cwd(
    repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Criterion 2 (plan §4.1, D-034): relative DATA_DIR and APP_DB_PATH start at the repo
    root, whatever the working directory is."""
    monkeypatch.chdir(tmp_path)
    settings = Settings.load(
        {"DATA_DIR": "./contracts/fixtures", "APP_DB_PATH": "./local/app.db"}, dotenv=False
    )
    assert settings.data_dir == (repo_root / "contracts" / "fixtures").resolve()
    assert settings.db_path == (repo_root / "local" / "app.db").resolve()


def test_relative_data_dir_cli_from_other_cwd(run_script, tmp_path: Path) -> None:
    """Criterion 2: `scrubgpt-app check` run from another folder with a relative DATA_DIR still
    finds the fixtures (relative to the repo root) → exit 0."""
    result = run_script("check", env={"DATA_DIR": "./contracts/fixtures"}, cwd=tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "case-fixture-01" in result.stdout + result.stderr


def test_data_dir_option_overrides_for_one_run(
    run_cli, data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Criterion 2: `--data-dir` overrides DATA_DIR for one run (and only that run)."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "missing"))
    code, out = run_cli("check", "--data-dir", str(data_dir))
    assert code == 0, out
    code, out = run_cli("check")
    assert code == 2, out


def test_relative_data_dir_option_resolves_against_repo_root(
    run_cli, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Criterion 2: a relative `--data-dir` also starts at the repo root (README)."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "missing"))
    code, out = run_cli("check", "--data-dir", "./contracts/fixtures")
    assert code == 0, out


@pytest.mark.parametrize("value", ["abc", "70000", "-5", "8000.5"])
def test_bad_app_port_is_a_clear_error(value: str) -> None:
    """Criterion 2: a bad APP_PORT gives a clear error that names the setting."""
    with pytest.raises(Exception) as info:
        Settings.load({"APP_PORT": value}, dotenv=False)
    assert "APP_PORT" in str(info.value)


@pytest.mark.parametrize("value", ["fake", "openai", "mocked"])
def test_bad_brain_mode_is_a_clear_error(value: str) -> None:
    """Criterion 2: a bad BRAIN_MODE gives a clear error that names the setting
    (CLAUDE.md rule 1: `mock` or `real`)."""
    with pytest.raises(Exception) as info:
        Settings.load({"BRAIN_MODE": value}, dotenv=False)
    assert "BRAIN_MODE" in str(info.value)


@pytest.mark.parametrize(
    ("name", "value"), [("APP_PORT", "abc"), ("APP_PORT", "70000"), ("BRAIN_MODE", "fake")]
)
def test_bad_setting_cli_exits_cleanly(run_script, name: str, value: str) -> None:
    """Criterion 2 through the command line: a bad setting is a clear message naming it, no
    Python traceback, and exit 2 (README: "2 the check couldn't run"; an uncaught exception
    exits 1, which would claim every check ran)."""
    result = run_script("check", env={"DATA_DIR": "./contracts/fixtures", name: value})
    out = result.stdout + result.stderr
    assert result.returncode == 2, out
    assert name in out
    assert "Traceback" not in out
