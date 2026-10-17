"""I1 acceptance: drop mode, a Friday drop checked file by file (brief criterion 5).

Sources: D-038 ("the loader checks a drop file by file ('drop mode') and loads only complete
packages"; contents: case JSON + clips + posters, `video.mp4` only for the golden cases),
app/server/CLAUDE.md rule 2 ("validates a Friday drop file by file and reports per file"),
app/server/README.md ("reports a drop per package and per file; `video.mp4` may be missing (a
warning), but such a package isn't loadable yet"; exit codes 0 all loadable, 1 not all, 2 the
check couldn't run), D-064 rule 2 (a missing `video.mp4` in a drop is a warning, "not loadable
until video.mp4 arrives"), the brief (accepts `<drop>/<case_id>/` and `<drop>/cases/<case_id>/`).
"""

from __future__ import annotations

from pathlib import Path

import pytest

CASE_ID = "case-fixture-01"
PACKAGE_FILES = (
    "case.json",
    "timeline.json",
    "moments.json",
    "questions.json",
    "seed_records.json",
    "poster.jpg",
)


@pytest.fixture
def drop_dir(tmp_path: Path) -> Path:
    folder = tmp_path / "drop" / "2026-10-30"
    folder.mkdir(parents=True)
    return folder


def _section(out: str, case_id: str, other_ids: list[str]) -> str:
    """The part of the report about one package (from its id up to the next package's id)."""
    start = out.find(case_id)
    assert start >= 0, f"{case_id} is not in the report:\n{out}"
    ends = [i for i in (out.find(o, start + len(case_id)) for o in other_ids) if i > start]
    return out[start : min(ends) if ends else len(out)]


def test_complete_drop_exit_0(
    run_cli, drop_dir: Path, clone_case, fixture_reference: Path, data_dir: Path
) -> None:
    """Criterion 5: a complete drop (`<drop>/<case_id>/`) → exit 0, the package is loadable."""
    clone_case(drop_dir, CASE_ID)
    code, out = run_cli(
        "drop", str(drop_dir), "--reference", str(fixture_reference), "--data-dir", str(data_dir)
    )
    assert code == 0, out
    assert CASE_ID in out
    assert "not loadable" not in out.lower()


def test_report_is_per_file(
    run_cli, drop_dir: Path, clone_case, fixture_reference: Path, data_dir: Path
) -> None:
    """Criterion 5 (D-038, rule 2: "reports per file"): the report names every package file it
    checked, not only the package."""
    clone_case(drop_dir, CASE_ID)
    code, out = run_cli(
        "drop", str(drop_dir), "--reference", str(fixture_reference), "--data-dir", str(data_dir)
    )
    assert code == 0, out
    for name in (*PACKAGE_FILES, "video.mp4"):
        assert name in out, f"{name} is not reported:\n{out}"
    assert "clips" in out


def test_missing_video_is_a_warning_and_not_loadable(
    run_cli, drop_dir: Path, clone_case, fixture_reference: Path, data_dir: Path, tree_digest
) -> None:
    """Criterion 5 (D-038, D-064 rule 2): a package without `video.mp4` → a warning on that file
    and "not loadable", exit 1; nothing in the drop is modified."""
    clone_case(drop_dir, CASE_ID, video=False)
    before = tree_digest(drop_dir)
    code, out = run_cli(
        "drop", str(drop_dir), "--reference", str(fixture_reference), "--data-dir", str(data_dir)
    )
    assert code == 1, out
    assert "video.mp4" in out
    assert "warn" in out.lower()
    assert "not loadable" in out.lower()
    assert tree_digest(drop_dir) == before


@pytest.mark.parametrize(
    ("file_name", "content"),
    [
        ("moments.json", '{"contract_version": "1.0", "moments": ['),
        ("questions.json", '{"contract_version": "1.0"}'),
        ("case.json", "\x00\x01 not json"),
    ],
)
def test_broken_file_is_named(
    run_cli,
    drop_dir: Path,
    clone_case,
    fixture_reference: Path,
    data_dir: Path,
    tree_digest,
    file_name: str,
    content: str,
) -> None:
    """Criterion 5: a broken file is named in the report; the package isn't loadable (exit 1);
    the file is not modified."""
    package = clone_case(drop_dir, CASE_ID)
    (package / file_name).write_text(content, encoding="utf-8")
    before = tree_digest(drop_dir)
    code, out = run_cli(
        "drop", str(drop_dir), "--reference", str(fixture_reference), "--data-dir", str(data_dir)
    )
    assert code == 1, out
    assert file_name in out
    assert "not loadable" in out.lower()
    assert tree_digest(drop_dir) == before


def test_missing_poster_is_an_error_not_a_warning(
    run_cli, drop_dir: Path, clone_case, fixture_reference: Path, data_dir: Path
) -> None:
    """Criterion 5 (D-064 rule 2: `poster.jpg`, `clips/` and the JSON stay required in a drop)."""
    package = clone_case(drop_dir, CASE_ID)
    (package / "poster.jpg").unlink()
    code, out = run_cli(
        "drop", str(drop_dir), "--reference", str(fixture_reference), "--data-dir", str(data_dir)
    )
    assert code == 1, out
    assert "poster.jpg" in out
    assert "not loadable" in out.lower()


def test_per_package_results_in_one_drop(
    run_cli, drop_dir: Path, clone_case, fixture_reference: Path, data_dir: Path
) -> None:
    """Criterion 5: a drop with several packages reports each one: a complete package is
    loadable, a package without video isn't, a broken one names its file; exit 1."""
    ids = ["case-fixture-01", "case-fixture-02", "case-fixture-03"]
    clone_case(drop_dir, ids[0])
    clone_case(drop_dir, ids[1], video=False)
    broken = clone_case(drop_dir, ids[2])
    (broken / "timeline.json").write_text("{", encoding="utf-8")
    code, out = run_cli(
        "drop", str(drop_dir), "--reference", str(fixture_reference), "--data-dir", str(data_dir)
    )
    assert code == 1, out
    first = _section(out, ids[0], ids[1:])
    second = _section(out, ids[1], [ids[0], ids[2]])
    third = _section(out, ids[2], ids[:2])
    assert "not loadable" not in first.lower(), out
    assert "video.mp4" in second and "not loadable" in second.lower(), out
    assert "timeline.json" in third and "not loadable" in third.lower(), out


def test_cases_subfolder_layout(
    run_cli, drop_dir: Path, clone_case, fixture_reference: Path, data_dir: Path
) -> None:
    """Criterion 5 (brief): `<drop>/cases/<case_id>/` is accepted like `<drop>/<case_id>/`."""
    clone_case(drop_dir / "cases", CASE_ID)
    code, out = run_cli(
        "drop", str(drop_dir), "--reference", str(fixture_reference), "--data-dir", str(data_dir)
    )
    assert code == 0, out
    assert CASE_ID in out


def test_cases_subfolder_layout_missing_video(
    run_cli, drop_dir: Path, clone_case, fixture_reference: Path, data_dir: Path
) -> None:
    """Criterion 5: the same per-file result in the `cases/` layout."""
    clone_case(drop_dir / "cases", CASE_ID, video=False)
    code, out = run_cli(
        "drop", str(drop_dir), "--reference", str(fixture_reference), "--data-dir", str(data_dir)
    )
    assert code == 1, out
    assert "video.mp4" in out and "not loadable" in out.lower()


def test_missing_drop_folder_exit_2(run_cli, tmp_path: Path, fixture_reference: Path) -> None:
    """Criterion 5: a missing drop folder → exit 2 (the check couldn't run)."""
    code, out = run_cli(
        "drop", str(tmp_path / "no-such-drop"), "--reference", str(fixture_reference)
    )
    assert code == 2, out


def test_missing_drop_folder_console_script(run_script, tmp_path: Path) -> None:
    """Criterion 5 with the documented command: exit 2 and no traceback."""
    result = run_script("drop", str(tmp_path / "no-such-drop"))
    assert result.returncode == 2, result.stdout + result.stderr
    assert "Traceback" not in result.stderr


def test_drop_via_console_script(
    run_script, drop_dir: Path, clone_case, fixture_reference: Path
) -> None:
    """Criterion 5 with the documented command `scrubgpt-app drop <folder> --reference FILE`."""
    clone_case(drop_dir, CASE_ID, video=False)
    result = run_script("drop", str(drop_dir), "--reference", str(fixture_reference))
    out = result.stdout + result.stderr
    assert result.returncode == 1, out
    assert "video.mp4" in out and "not loadable" in out.lower()
