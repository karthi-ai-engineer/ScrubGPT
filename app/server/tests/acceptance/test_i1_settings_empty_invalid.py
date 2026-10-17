"""I1 acceptance: settings, re-test criterion 2 (changed at 00ce6e4).

Criterion 2 (brief, re-test): "Settings: environment > repo-root `.env` > defaults; an **empty
value counts as unset** (the next layer or the default applies); relative paths resolve against
the repo root; `--data-dir` overrides for one run. `APP_PORT` outside 1–65535 or not a number, and
`BRAIN_MODE` other than `mock`/`real`, are a clear error naming the setting: `Settings.load`
raises `ValueError` naming it, and every `scrubgpt-app` command prints a message naming it and
exits **2**, with no traceback."

Also app/server/README.md (Usage, settings paragraph): "An empty value (`APP_PORT=`) counts as
unset … An invalid value (`APP_PORT` not 1–65535, `BRAIN_MODE` not `mock`/`real`) stops every
command with a message naming the setting (exit 2)."
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scrubgpt_app.settings import Settings

COMMANDS = ("serve", "check", "drop")


def _write_dotenv(root: Path, **values: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / ".env").write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")
    return root


def _args(command: str, tmp_path: Path) -> list[str]:
    """Arguments for each documented command (a drop folder that exists, so only the setting can
    stop it)."""
    if command == "drop":
        drop = tmp_path / "drop" / "2026-10-30"
        drop.mkdir(parents=True, exist_ok=True)
        return ["drop", str(drop)]
    return [command]


# --- an empty value counts as unset -------------------------------------------------------


@pytest.mark.parametrize("name", ["APP_PORT", "BRAIN_MODE", "DATA_DIR"])
def test_empty_environment_value_falls_back_to_dotenv(name: str, tmp_path: Path) -> None:
    """Criterion 2: an empty environment value counts as unset, so the `.env` value applies."""
    data = tmp_path / "dotenv-data"
    root = _write_dotenv(tmp_path / "root", DATA_DIR=str(data), APP_PORT="8123", BRAIN_MODE="real")
    settings = Settings.load({name: ""}, root=root)
    assert settings.port == 8123
    assert str(settings.brain_mode) == "real"
    assert settings.data_dir == data.resolve()


@pytest.mark.parametrize("name", ["APP_PORT", "BRAIN_MODE", "DATA_DIR"])
def test_empty_dotenv_value_falls_back_to_default(name: str, tmp_path: Path) -> None:
    """Criterion 2: an empty `.env` value counts as unset, so the default applies
    (DATA_DIR ./contracts/fixtures at the repo root `root`, APP_PORT 8000, BRAIN_MODE mock)."""
    root = _write_dotenv(tmp_path / "root", **{name: ""})
    settings = Settings.load({}, root=root)
    assert settings.port == 8000
    assert str(settings.brain_mode) == "mock"
    assert settings.data_dir == (root / "contracts" / "fixtures").resolve()


def test_empty_in_both_layers_gives_the_defaults(tmp_path: Path) -> None:
    """Criterion 2: empty in the environment and in `.env` → the defaults (relative to the
    repo root given as `root`)."""
    root = _write_dotenv(tmp_path / "root", APP_PORT="", BRAIN_MODE="", DATA_DIR="")
    settings = Settings.load({"APP_PORT": "", "BRAIN_MODE": "", "DATA_DIR": ""}, root=root)
    assert settings.port == 8000
    assert str(settings.brain_mode) == "mock"
    assert settings.data_dir == (root / "contracts" / "fixtures").resolve()


def test_empty_environment_value_does_not_hide_a_bad_dotenv_value(tmp_path: Path) -> None:
    """Criterion 2: the empty environment value is unset, so the next layer (`.env`) applies,
    and an invalid value there is still the clear `ValueError` naming the setting."""
    root = _write_dotenv(tmp_path / "root", APP_PORT="abc")
    with pytest.raises(ValueError, match="APP_PORT"):
        Settings.load({"APP_PORT": ""}, root=root)


def test_empty_values_through_the_command(run_script) -> None:
    """Criterion 2 with the documented command: `APP_PORT=`, `BRAIN_MODE=` and `DATA_DIR=` are
    unset, so `scrubgpt-app check` uses the defaults (the fixture DATA_DIR, D-026) → exit 0."""
    result = run_script("check", env={"APP_PORT": "", "BRAIN_MODE": "", "DATA_DIR": ""})
    out = result.stdout + result.stderr
    assert result.returncode == 0, out
    assert "case-fixture-01" in out
    assert "Traceback" not in out


# --- Settings.load raises ValueError naming the setting ----------------------------------


@pytest.mark.parametrize("value", ["abc", "0", "65536", "70000", "-5", "8000.5", "80 80"])
def test_bad_app_port_raises_value_error(value: str) -> None:
    """Criterion 2: `APP_PORT` outside 1–65535 or not a number → `ValueError` naming APP_PORT."""
    with pytest.raises(ValueError, match="APP_PORT"):
        Settings.load({"APP_PORT": value}, dotenv=False)


@pytest.mark.parametrize("value", ["1", "65535"])
def test_app_port_range_is_inclusive(value: str) -> None:
    """Criterion 2: 1 and 65535 are inside the allowed range 1–65535."""
    assert Settings.load({"APP_PORT": value}, dotenv=False).port == int(value)


@pytest.mark.parametrize("value", ["fake", "openai", "mocked", "none"])
def test_bad_brain_mode_raises_value_error(value: str) -> None:
    """Criterion 2: `BRAIN_MODE` other than `mock`/`real` → `ValueError` naming BRAIN_MODE."""
    with pytest.raises(ValueError, match="BRAIN_MODE"):
        Settings.load({"BRAIN_MODE": value}, dotenv=False)


@pytest.mark.parametrize(("name", "value"), [("APP_PORT", "70000"), ("BRAIN_MODE", "fake")])
def test_bad_dotenv_value_raises_value_error(name: str, value: str, tmp_path: Path) -> None:
    """Criterion 2: the same `ValueError` when the bad value comes from the repo-root `.env`."""
    root = _write_dotenv(tmp_path / "root", **{name: value})
    with pytest.raises(ValueError, match=name):
        Settings.load({}, root=root)


# --- every scrubgpt-app command: a message naming it, exit 2, no traceback ---------------


@pytest.mark.parametrize("command", COMMANDS)
@pytest.mark.parametrize(
    ("name", "value"),
    [("APP_PORT", "abc"), ("APP_PORT", "0"), ("APP_PORT", "65536"), ("BRAIN_MODE", "fake")],
)
def test_every_command_in_process_exits_2(
    run_cli, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, command: str, name: str, value: str
) -> None:
    """Criterion 2: every `scrubgpt-app` command (`scrubgpt_app.cli.main`) prints a message
    naming the invalid setting and returns 2."""
    monkeypatch.setenv(name, value)
    code, out = run_cli(*_args(command, tmp_path))
    assert code == 2, out
    assert name in out


@pytest.mark.parametrize("command", COMMANDS)
@pytest.mark.parametrize(("name", "value"), [("APP_PORT", "-5"), ("BRAIN_MODE", "openai")])
def test_every_command_console_script_exits_2(
    run_script_bounded, tmp_path: Path, command: str, name: str, value: str
) -> None:
    """Criterion 2 with the installed `scrubgpt-app` script: every command (also `serve`, which
    must not start) prints a message naming the setting, exits 2, and shows no traceback."""
    code, out = run_script_bounded(
        *_args(command, tmp_path), env={"DATA_DIR": "./contracts/fixtures", name: value}
    )
    assert code is not None, f"`scrubgpt-app {command}` was still running:\n{out}"
    assert code == 2, out
    assert name in out
    assert "Traceback" not in out
