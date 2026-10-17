"""Dev1's unit tests for B4, the case registry (pipeline/cases.py)."""

import json
from pathlib import Path

import pytest
import yaml
from scrubgpt_brain import cli
from scrubgpt_brain.pipeline import cases as c
from scrubgpt_contracts.models.case_package import Case, CaseStatus

ENTRY = {
    "id": "yt-ja-01",
    "title": {"ja": "ロボット支援前立腺全摘除術（中葉あり）", "en": "RARP with a median lobe"},
    "source": "youtube",
    "source_url": "https://www.youtube.com/watch?v=example",
    "language": "ja",
    "video_type": "edited",
    "narrated": True,
    "synthetic_speech": False,
    "default_step_track": "ai",
}


def write_registry(path: Path, entries: list) -> Path:
    path.write_text(yaml.safe_dump(entries, allow_unicode=True), encoding="utf-8")
    return path


def test_build_case_fills_the_contract_and_the_default_data_note():
    case = c.build_case(ENTRY, 1534.2)
    assert isinstance(case, Case) and case.duration_s == 1534.2
    assert case.status is CaseStatus.PARTIAL and case.contract_version == "1.0"
    assert case.data_note.en == c.DEFAULT_DATA_NOTES["youtube"]["en"]
    own = c.build_case({**ENTRY, "data_note": {"ja": "独自", "en": "own"}}, 10.0)
    assert own.data_note.en == "own"


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"language": "fr"}, "language"),
        ({"title": {"ja": "", "en": "x"}}, "title"),
        ({"id": "YT JA 01"}, "id"),
        ({"language": "none", "narrated": True}, "(entry)"),  # no speech, yet narrated (D-049)
    ],
)
def test_invalid_entries_name_the_case_and_field(change, field):
    with pytest.raises(c.RegistryError) as info:
        c.build_case({**ENTRY, **change}, 60.0)
    assert any(field in problem for problem in info.value.problems)


def test_registry_loading_and_its_problems(tmp_path: Path):
    good = write_registry(tmp_path / "cases.yaml", [ENTRY, {**ENTRY, "id": "yt-en-01"}])
    assert sorted(c.load_registry(good)) == ["yt-en-01", "yt-ja-01"]
    bad = write_registry(
        tmp_path / "bad.yaml", [ENTRY, ENTRY, {"title": "no id"}, {**ENTRY, "id": "x", "foo": 1}]
    )
    with pytest.raises(c.RegistryError) as info:
        c.load_registry(bad)
    text = str(info.value)
    assert "yt-ja-01: duplicate case id" in text and "entry 2: needs an `id`" in text
    assert "x: unknown field(s) ['foo']" in text
    (tmp_path / "list.yaml").write_text("id: not-a-list", encoding="utf-8")
    with pytest.raises(c.RegistryError, match="must be a list"):
        c.load_registry(tmp_path / "list.yaml")


def test_write_case_is_atomic_and_round_trips(tmp_path: Path):
    path = c.write_case(c.build_case(ENTRY, 100.0), tmp_path / "work" / "yt-ja-01")
    assert path.name == "case.json" and not (path.parent / "case.json.part").exists()
    assert Case.model_validate_json(path.read_text("utf-8")).id == "yt-ja-01"
    assert json.loads(path.read_text("utf-8"))["title"]["ja"].startswith("ロボット")


def test_register_case_measures_the_video(media, tmp_path: Path):
    video = media.video(tmp_path / "video.mp4", duration=7)
    registry = write_registry(tmp_path / "cases.yaml", [ENTRY])
    path = c.register_case(registry, "yt-ja-01", video, tmp_path / "work")
    assert abs(json.loads(path.read_text("utf-8"))["duration_s"] - 7.0) < 0.2
    with pytest.raises(c.RegistryError, match="no entry for case `nope`"):
        c.register_case(registry, "nope", video, tmp_path / "work")


def test_cli_case(media, tmp_path: Path):
    video = media.video(tmp_path / "video.mp4", duration=4)
    registry = write_registry(tmp_path / "cases.yaml", [ENTRY])
    lines: list[str] = []
    args = ["case", str(registry), "yt-ja-01", str(video), str(tmp_path / "work")]
    assert cli.main(args, out=lines.append) == 0 and (tmp_path / "work" / "case.json").is_file()
    bad = ["case", str(registry), "nope", str(video), str(tmp_path / "work")]
    assert cli.main(bad, out=lines.append, err=lines.append) == 1
    assert "no entry for case `nope`" in lines[-1]
