"""Settings: defaults, `.env`, environment, paths relative to the repo root."""

from pathlib import Path

import pytest
from scrubgpt_app.settings import BrainMode, Settings, read_dotenv


def test_defaults_point_at_the_fixtures(tmp_path: Path) -> None:
    settings = Settings.load({}, root=tmp_path, dotenv=False)
    assert settings.data_dir == (tmp_path / "contracts" / "fixtures").resolve()
    assert (
        settings.db_path == (tmp_path / "app" / "server" / ".local" / "scrubgpt.sqlite").resolve()
    )
    assert settings.port == 8000
    assert settings.brain_mode is BrainMode.MOCK
    assert settings.cases_dir == settings.data_dir / "cases"
    assert settings.reference_dir == settings.data_dir / "reference"


def test_dotenv_then_environment(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "# comment\n\nDATA_DIR='./data'\nexport APP_PORT=9000\nBRAIN_MODE=real\nnot a line\n",
        encoding="utf-8",
    )
    settings = Settings.load({"APP_PORT": "9100"}, root=tmp_path)
    assert settings.data_dir == (tmp_path / "data").resolve()
    assert settings.port == 9100  # the environment wins over .env
    assert settings.brain_mode is BrainMode.REAL


def test_absolute_paths_stay(tmp_path: Path) -> None:
    settings = Settings.load({"DATA_DIR": str(tmp_path / "x")}, root=tmp_path, dotenv=False)
    assert settings.data_dir == tmp_path / "x"


@pytest.mark.parametrize(("key", "value"), [("APP_PORT", "eight"), ("BRAIN_MODE", "fake")])
def test_bad_values_are_named(tmp_path: Path, key: str, value: str) -> None:
    with pytest.raises(ValueError, match=key):
        Settings.load({key: value}, root=tmp_path, dotenv=False)


def test_missing_dotenv_is_empty(tmp_path: Path) -> None:
    assert read_dotenv(tmp_path / ".env") == {}
