"""B4 Case registry (plan §2.2): one `case.json` per case, from a registry the team keeps.

`case.json` is a case's identity card in the App:
- its bilingual title;
- where the video comes from (GraSP, PSI-AVA, YouTube, synthetic);
- the spoken language, and whether it is narrated or uses synthetic speech;
- whether the video is full-length or edited (an edited video never produces duration-based
  deviations, E2);
- which step track to show by default;
- a data note on where the data comes from and how it may be used.

The team keeps one **registry** (YAML, in `DATA_DIR`, never in git: it holds video URLs and
notes), with one entry per case. B4 combines an entry with the duration of the case's normalised
`video.mp4` (B3), validates the result with the contract's `Case` model and writes `case.json`
atomically into the folder the caller gives. Normally that is `<DATA_DIR>/work/<case_id>/`; only a
complete, valid package is later copied into `cases/` (brain/CLAUDE.md rule 4).
"""

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError
from scrubgpt_contracts.models.case_package import Case, CaseStatus
from scrubgpt_contracts.models.common import CONTRACT_VERSION

from scrubgpt_brain.engines.media import probe

CASE_FILE = "case.json"
REGISTRY_FIELDS = (
    "id",
    "title",
    "source",
    "source_url",
    "language",
    "video_type",
    "narrated",
    "synthetic_speech",
    "default_step_track",
    "data_note",
)
"""What a registry entry holds: every `case.json` field except `duration_s` (measured from the
video), `status` (set by the pipeline) and `contract_version`."""

DEFAULT_DATA_NOTES: Mapping[str, dict[str, str]] = {
    "youtube": {
        "ja": "YouTubeの公開動画です。社内デモ専用で、再配布しません。",
        "en": "A public YouTube video, for private internal demo use only; never redistributed.",
    },
    "grasp": {
        "ja": "GraSPデータセット（Ayobi et al. 2024）。正解ラベル付き。"
        "データセットの利用条件に従い社内デモ専用。",
        "en": "GraSP dataset (Ayobi et al. 2024), with ground-truth labels; internal demo use "
        "only, under the dataset's terms.",
    },
    "psi-ava": {
        "ja": "PSI-AVAデータセット。データセットの利用条件に従い社内デモ専用。",
        "en": "PSI-AVA dataset; internal demo use only, under the dataset's terms.",
    },
    "synthetic": {
        "ja": "合成データです。手術映像や患者データは含みません。",
        "en": "Synthetic data, with no surgical video or patient data.",
    },
}
"""Used when an entry has no `data_note` of its own."""


class RegistryError(ValueError):
    """The registry is missing, unreadable, or an entry is invalid. `problems` lists each one."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("case registry problems:\n" + "\n".join(f"- {p}" for p in problems))


def load_registry(path: Path) -> dict[str, dict[str, Any]]:
    """The registry's entries by case id. The file is a YAML list of entries (`REGISTRY_FIELDS`;
    `data_note` may be left out). Raises `RegistryError` listing every problem."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise RegistryError([f"{path}: can't read it as YAML: {exc}"]) from None
    if not isinstance(data, list):
        raise RegistryError([f"{path}: the registry must be a list of case entries"])
    entries: dict[str, dict[str, Any]] = {}
    problems = []
    for i, entry in enumerate(data):
        if not isinstance(entry, dict) or not entry.get("id"):
            problems.append(f"{path}: entry {i}: needs an `id`")
            continue
        case_id = str(entry["id"])
        if case_id in entries:
            problems.append(f"{path}: {case_id}: duplicate case id")
        unknown = sorted(set(entry) - set(REGISTRY_FIELDS))
        if unknown:
            problems.append(f"{path}: {case_id}: unknown field(s) {unknown}")
        entries[case_id] = entry
    if problems:
        raise RegistryError(problems)
    return entries


def build_case(
    entry: Mapping[str, Any], duration_s: float, *, status: CaseStatus = CaseStatus.PARTIAL
) -> Case:
    """The `case.json` model for a registry entry and the normalised video's duration.

    Raises `RegistryError` naming the case and every field the contract rejects.
    """
    data = {field: entry.get(field) for field in REGISTRY_FIELDS}
    if data["data_note"] is None:
        data["data_note"] = DEFAULT_DATA_NOTES.get(str(entry.get("source")))
    data.update(contract_version=CONTRACT_VERSION, duration_s=duration_s, status=status.value)
    try:
        return Case.model_validate(data)
    except ValidationError as exc:
        case_id = entry.get("id", "(no id)")
        problems = [
            f"{case_id}: {'.'.join(str(p) for p in err['loc']) or '(entry)'}: {err['msg']}"
            for err in exc.errors(include_url=False)
        ]
        raise RegistryError(problems) from None


def write_case(case: Case, out_dir: Path) -> Path:
    """Write `case.json` into `out_dir` atomically and return its path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / CASE_FILE
    part = out_dir / f"{CASE_FILE}.part"
    text = json.dumps(case.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
    part.write_text(text, encoding="utf-8", newline="\n")
    os.replace(part, target)
    return target


def register_case(
    registry: Path,
    case_id: str,
    video: Path,
    out_dir: Path,
    *,
    status: CaseStatus = CaseStatus.PARTIAL,
) -> Path:
    """`case.json` for one registry entry, with `duration_s` measured from the normalised video."""
    entries = load_registry(registry)
    if case_id not in entries:
        raise RegistryError([f"{registry}: no entry for case `{case_id}`"])
    duration = probe(video).duration_s
    return write_case(build_case(entries[case_id], duration, status=status), out_dir)
