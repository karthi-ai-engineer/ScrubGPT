"""Settings from the environment and the repo-root `.env` (CLAUDE.md "Data and secrets").

Relative paths (`DATA_DIR`, `APP_DB_PATH`) resolve against the **repo root**, wherever the server
is started from. Environment variables win over `.env`. The app server never needs an OpenAI key.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
"""`app/server/scrubgpt_app/settings.py` → the repo root."""

DEFAULTS = {
    # Dev2 works on the fixtures until integration (D-026).
    "DATA_DIR": "./contracts/fixtures",
    "APP_DB_PATH": "./app/server/.local/scrubgpt.sqlite",
    "APP_PORT": "8000",
    "BRAIN_MODE": "mock",
    "MOCK_BRAIN_URL": "http://localhost:8101",
    "BRAIN_URL": "http://localhost:8100",
}


class BrainMode(StrEnum):
    """Which Brain the Brain client calls (I7): the fake Brain (:8101) or the real one (:8100)."""

    MOCK = "mock"
    REAL = "real"


def read_dotenv(path: Path) -> dict[str, str]:
    """`KEY=VALUE` lines of a `.env` file; blank lines, comments and malformed lines are skipped.
    A missing or unreadable file gives `{}`."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return {}
    values: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def resolve(path: str, root: Path = REPO_ROOT) -> Path:
    """An absolute path, with a relative one taken from the repo root."""
    candidate = Path(path).expanduser()
    return candidate if candidate.is_absolute() else (root / candidate).resolve()


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    """Holds `cases/<case_id>/` and `reference/<procedure_id>.json` (plan §4.2, §4.2b)."""
    db_path: Path
    """The local SQLite file (I2). Never inside the Google Drive folder."""
    port: int
    brain_mode: BrainMode
    mock_brain_url: str
    brain_url: str
    web_dist: Path
    """The built web app (`app/web/dist`), served at `/` when it exists."""

    @property
    def cases_dir(self) -> Path:
        return self.data_dir / "cases"

    @property
    def reference_dir(self) -> Path:
        return self.data_dir / "reference"

    @classmethod
    def load(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        root: Path = REPO_ROOT,
        dotenv: bool = True,
    ) -> "Settings":
        """Defaults, then the repo-root `.env`, then `environ` (default: `os.environ`)."""
        values = dict(DEFAULTS)
        if dotenv:
            values.update(read_dotenv(root / ".env"))
        values.update(os.environ if environ is None else environ)
        try:
            port = int(values["APP_PORT"])
        except ValueError:
            raise ValueError(f"APP_PORT must be a number, not {values['APP_PORT']!r}") from None
        try:
            brain_mode = BrainMode(values["BRAIN_MODE"])
        except ValueError:
            raise ValueError(
                f"BRAIN_MODE must be 'mock' or 'real', not {values['BRAIN_MODE']!r}"
            ) from None
        return cls(
            data_dir=resolve(values["DATA_DIR"], root),
            db_path=resolve(values["APP_DB_PATH"], root),
            port=port,
            brain_mode=brain_mode,
            mock_brain_url=values["MOCK_BRAIN_URL"],
            brain_url=values["BRAIN_URL"],
            web_dist=root / "app" / "web" / "dist",
        )
