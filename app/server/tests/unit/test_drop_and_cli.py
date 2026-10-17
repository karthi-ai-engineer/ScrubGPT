"""Drop mode (D-038), file by file, and the `scrubgpt-app` command line."""

import json
import shutil
from pathlib import Path

import pytest
from scrubgpt_app.cli import main
from scrubgpt_app.drop import check_drop
from scrubgpt_app.settings import REPO_ROOT

FIXTURES = REPO_ROOT / "contracts" / "fixtures"
CASE_ID = "case-fixture-01"
FIXTURE_CASE = FIXTURES / "cases" / CASE_ID
FIXTURE_REFERENCE = FIXTURES / "reference" / "rarp.json"


@pytest.fixture
def drop(tmp_path: Path) -> Path:
    folder = tmp_path / "drop" / "2026-10-30"
    shutil.copytree(FIXTURE_CASE, folder / CASE_ID)
    return folder


def run(*argv: str) -> tuple[int, str]:
    lines: list[str] = []
    return main(list(argv), out=lines.append), "\n".join(lines)


def test_a_complete_drop_is_loadable(drop: Path) -> None:
    (package,) = check_drop(drop, FIXTURE_REFERENCE)
    assert package.loadable
    assert {result.status for result in package.files.values()} == {"ok"}
    code, text = run("drop", str(drop), "--reference", str(FIXTURE_REFERENCE))
    assert code == 0 and f"{CASE_ID}: LOADABLE" in text


def test_a_drop_without_video_is_reported_per_file(drop: Path) -> None:
    (drop / CASE_ID / "video.mp4").unlink()
    (package,) = check_drop(drop, FIXTURE_REFERENCE)
    assert not package.loadable
    assert package.files["video.mp4"].status == "warning"
    assert package.files["case.json"].status == "ok"
    code, text = run("drop", str(drop), "--reference", str(FIXTURE_REFERENCE))
    assert code == 1 and "NOT LOADABLE" in text and "WARNING video.mp4" in text


def test_a_broken_file_is_named(drop: Path) -> None:
    seeds = drop / CASE_ID / "seed_records.json"
    data = json.loads(seeds.read_text(encoding="utf-8"))
    data["records"][0]["question_id"] = "case-fixture-01.m01.q9"  # not in questions.json
    seeds.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    (package,) = check_drop(drop, FIXTURE_REFERENCE)
    assert package.files["seed_records.json"].status == "error"
    assert package.files["moments.json"].status == "ok"


def test_drop_cases_subfolder_and_reference_lookup(tmp_path: Path) -> None:
    folder = tmp_path / "drop"
    shutil.copytree(FIXTURE_CASE, folder / "cases" / CASE_ID)
    shutil.copytree(FIXTURES / "reference", folder / "reference")
    code, text = run("drop", str(folder))
    assert code == 0, text


def test_drop_folder_missing_is_exit_2(tmp_path: Path) -> None:
    code, text = run("drop", str(tmp_path / "nope"))
    assert code == 2 and "not a folder" in text


def test_check_the_fixtures() -> None:
    code, text = run("check", "--data-dir", str(FIXTURES))
    assert code == 0
    assert f"LOADED   {CASE_ID}" in text and "1 loaded, 0 rejected" in text


def test_check_reports_rejected_packages(data_dir: Path) -> None:
    (data_dir / "cases" / CASE_ID / "timeline.json").unlink()
    code, text = run("check", "--data-dir", str(data_dir))
    assert code == 1 and f"REJECTED {CASE_ID}" in text and "timeline.json" in text


def test_check_missing_data_dir_is_exit_2(tmp_path: Path) -> None:
    code, _ = run("check", "--data-dir", str(tmp_path / "nope"))
    assert code == 2


@pytest.mark.parametrize(("key", "value"), [("APP_PORT", "abc"), ("BRAIN_MODE", "fake")])
def test_a_bad_setting_is_a_clear_exit_2(
    monkeypatch: pytest.MonkeyPatch, key: str, value: str
) -> None:
    monkeypatch.setenv(key, value)
    code, text = run("check", "--data-dir", str(FIXTURES))
    assert code == 2 and "invalid setting" in text and key in text


@pytest.mark.parametrize("port", ["0", "70000", "abc"])
def test_serve_port_out_of_range_is_exit_2(port: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["serve", "--port", port])
    assert exit_info.value.code == 2
    assert "--port" in capsys.readouterr().err
