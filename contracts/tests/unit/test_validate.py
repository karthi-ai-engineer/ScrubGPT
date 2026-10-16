"""Dev1's unit tests for validate.py (`scrubgpt-validate`, plan §4.5, D-037)."""

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import pytest
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel
from scrubgpt_contracts import validate as v
from scrubgpt_contracts.models.common import (
    CONTRACT_VERSION,
    ContractModel,
    ErrorCode,
    NonEmptyStr,
    VersionedModel,
    api_error,
)

FIXTURES = Path(v.__file__).resolve().parent.parent / "fixtures"
CASE = "case-fixture-01"


def run(argv: list[str]) -> tuple[int, str]:
    lines: list[str] = []
    code = v.main(argv, out=lines.append)
    return code, "\n".join(lines)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """A copy of the fixture DATA_DIR (cases/ + reference/) to break."""
    shutil.copytree(FIXTURES / "cases" / CASE, tmp_path / "cases" / CASE)
    shutil.copytree(FIXTURES / "reference", tmp_path / "reference")
    return tmp_path


def edit(path: Path, change) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def errors_of(report: v.Report) -> str:
    return "\n".join(str(issue) for issue in report.errors)


# ── case and reference ────────────────────────────────────────────────────────


def test_fixture_case_and_reference_pass():
    code, text = run(["case", str(FIXTURES / "cases" / CASE)])
    assert code == 0, text
    assert "PASS: 0 error(s), 0 warning(s)" in text
    code, text = run(["reference", str(FIXTURES / "reference" / "rarp.json")])
    assert code == 0, text


def test_copied_case_passes(data_dir):
    assert v.validate_case(data_dir / "cases" / CASE).ok


def test_missing_required_file_and_clip(data_dir):
    case = data_dir / "cases" / CASE
    (case / "questions.json").unlink()
    (case / "clips" / f"{CASE}.m01.mp4").unlink()
    report = v.validate_case(case)
    assert "questions.json: required file is missing" in errors_of(report)
    assert f"{CASE}.m01: clips/{CASE}.m01.mp4 is missing" in errors_of(report)


def test_invalid_json_is_reported_per_file(data_dir):
    case = data_dir / "cases" / CASE
    (case / "timeline.json").write_text("{not json", encoding="utf-8")
    load = v.load_case(case)
    assert not load.file_ok("timeline.json")
    assert load.file_ok("moments.json")  # other files are still checked on their own
    assert any(issue.where == "timeline.json" for issue in load.report.errors)


def test_ids_must_exist_in_the_reference(data_dir):
    case = data_dir / "cases" / CASE
    edit(case / "moments.json", lambda d: d["moments"][0].update(step_id="rarp.p13.s09"))
    edit(
        case / "moments.json",
        lambda d: d["moments"][1].update(draft_obstacle="anatomical_variation.unknown_leaf"),
    )
    text = errors_of(v.validate_case(case))
    assert "step rarp.p13.s09 is not in the Procedure Reference" in text
    assert "obstacle anatomical_variation.unknown_leaf is not in the Procedure Reference" in text


def test_reference_found_by_prefix_or_given(data_dir, tmp_path):
    case = data_dir / "cases" / CASE
    moved = tmp_path / "elsewhere.json"
    (data_dir / "reference" / "rarp.json").rename(moved)
    report = v.validate_case(case)
    assert not report.errors and report.exit_code == 2  # could not finish, not an invalid package
    assert "Procedure Reference not found" in report.blocked[0]
    assert v.validate_case(case, reference_path=moved).ok
    code, text = run(["case", str(case), "--reference", str(tmp_path / "nope.json")])
    assert code == 2 and "CANNOT FINISH" in text


def test_a_missing_reference_wins_over_errors(data_dir):
    """D-052: exit 2 wins over 1, and the checks that could run are still reported."""
    case = data_dir / "cases" / CASE
    (data_dir / "reference" / "rarp.json").unlink()
    (case / "clips" / f"{CASE}.m01.jpg").unlink()
    report = v.validate_case(case)
    assert report.exit_code == 2
    assert f"clips/{CASE}.m01.jpg is missing" in errors_of(report)


def test_data_dir_env_var_is_not_used(data_dir, monkeypatch):
    case = data_dir / "cases" / CASE
    (data_dir / "reference" / "rarp.json").unlink()
    monkeypatch.setenv("DATA_DIR", str(FIXTURES))
    assert v.validate_case(case).exit_code == 2


def test_mixed_procedure_prefixes(data_dir):
    case = data_dir / "cases" / CASE
    edit(case / "moments.json", lambda d: d["moments"][3].update(step_id="lap.p09.s02"))
    report = v.validate_case(case)
    assert report.exit_code == 1
    assert "step ids from several procedures: ['lap', 'rarp']" in errors_of(report)
    given = v.validate_case(case, reference_path=data_dir / "reference" / "rarp.json")
    assert "step lap.p09.s02 is not in the Procedure Reference" in errors_of(given)


def test_upload_content_types_are_fixed():
    assert v.AUDIO_TYPES[".m4a"] == "audio/mp4"
    assert v.AUDIO_TYPES[".webm"] == "audio/webm"


def test_times_must_stay_within_the_video(data_dir):
    case = data_dir / "cases" / CASE
    edit(case / "case.json", lambda d: d.update(duration_s=100.0))
    text = errors_of(v.validate_case(case))
    assert f"{CASE}.m06 ends at 300.0 s, after the video (100.0 s)" in text


def test_case_identity(data_dir):
    case = data_dir / "cases" / CASE
    renamed = case.parent / "case-fixture-02"
    case.rename(renamed)
    text = errors_of(v.validate_case(renamed))
    assert "doesn't match the folder case-fixture-02" in text


def test_questions_and_records_point_to_existing_items(data_dir):
    case = data_dir / "cases" / CASE

    def break_question(data):
        data["operating"][0]["quote"] = None
        data["operating"][0]["type"] = "cue"
        data["operating"][0]["id"] = f"{CASE}.m09.q1"
        data["operating"][0]["moment_id"] = f"{CASE}.m09"

    edit(case / "questions.json", break_question)
    edit(case / "seed_records.json", lambda d: d["records"][0].update(moment_id=f"{CASE}.m08"))
    text = errors_of(v.validate_case(case))
    assert f"moment {CASE}.m09 doesn't exist" in text
    assert f"moment {CASE}.m08 doesn't exist" in text


def test_seed_records_must_be_grounded(data_dir):
    case = data_dir / "cases" / CASE
    edit(case / "seed_records.json", lambda d: d["records"][0].update(grounding=[]))
    assert "filled fields without grounding (G5)" in errors_of(v.validate_case(case))


def test_rank_order_is_only_a_warning(data_dir):
    case = data_dir / "cases" / CASE
    edit(case / "moments.json", lambda d: d["moments"].reverse())
    report = v.validate_case(case)
    assert report.ok
    assert any("descending score" in issue.message for issue in report.warnings)


def test_reference_file_name_must_match_its_id(tmp_path):
    wrong = tmp_path / "lap.json"
    shutil.copy(FIXTURES / "reference" / "rarp.json", wrong)
    report = v.validate_reference(wrong)
    assert "must be rarp.json" in errors_of(report)


def test_not_a_folder_cannot_run(tmp_path):
    code, text = run(["case", str(tmp_path / "nope")])
    assert code == 2 and "cannot run" in text


# ── Brain API: response and live, with a stand-in registry ────────────────────


class Health(VersionedModel):
    """Stand-in /health response."""

    status: str


class EchoRequest(ContractModel):
    """Stand-in JSON request."""

    text: NonEmptyStr


class EchoResponse(VersionedModel):
    """Stand-in JSON response."""

    text: str


class UploadRequest(ContractModel):
    """Stand-in multipart form fields."""

    lang_hint: str


class UploadResponse(VersionedModel):
    """Stand-in multipart response."""

    size: int


@dataclass(frozen=True)
class Endpoint:
    method: str
    path: str
    request: type[BaseModel] | None
    response: type[BaseModel]
    files: tuple[str, ...] = ()


ENDPOINTS = {
    "health": Endpoint("GET", "/health", None, Health),
    "echo": Endpoint("POST", "/v1/echo", EchoRequest, EchoResponse),
    "upload": Endpoint("POST", "/v1/upload", UploadRequest, UploadResponse, ("audio",)),
}


def make_app(*, map_422: bool = True, version: bool = True) -> FastAPI:
    app = FastAPI()
    if map_422:

        @app.exception_handler(RequestValidationError)
        async def bad_request(_request, exc):
            body = api_error(ErrorCode.BAD_REQUEST, str(exc)[:200]).model_dump(mode="json")
            return JSONResponse(body, status_code=400)

    extra = {"contract_version": CONTRACT_VERSION} if version else {}

    @app.get("/health")
    def health():
        return {**extra, "status": "ok"}

    @app.post("/v1/echo")
    def echo(request: EchoRequest):
        return {**extra, "text": request.text}

    @app.post("/v1/upload")
    async def upload(audio: Annotated[UploadFile, File()], lang_hint: Annotated[str, Form()]):
        return {**extra, "size": len(await audio.read())}

    return app


@pytest.fixture
def api_fixtures(tmp_path: Path) -> Path:
    folder = tmp_path / "brain_api"
    folder.mkdir()
    (folder / "echo.request.json").write_text('{"text": "こんにちは"}', encoding="utf-8")
    (folder / "upload.request.json").write_text('{"lang_hint": "auto"}', encoding="utf-8")
    (folder / "upload.request.audio.m4a").write_bytes(b"\x00" * 64)
    return folder


def test_live_passes_against_a_conforming_brain(api_fixtures):
    with TestClient(make_app()) as client:
        report = v.run_live(client, ENDPOINTS, api_fixtures)
    assert report.ok, report.render()
    assert len(report.checked) == 5  # 3 calls + 2 empty-request probes


def test_live_needs_contract_version_and_400_errors(api_fixtures):
    with TestClient(make_app(version=False)) as client:
        report = v.run_live(client, ENDPOINTS, api_fixtures)
    assert "has no contract_version" in errors_of(report)
    with TestClient(make_app(map_422=False)) as client:
        report = v.run_live(client, ENDPOINTS, api_fixtures)
    assert "expected HTTP 400 bad_request, got 422" in errors_of(report)


def test_live_checks_its_request_fixtures(api_fixtures):
    (api_fixtures / "echo.request.json").write_text('{"text": ""}', encoding="utf-8")
    (api_fixtures / "upload.request.audio.m4a").unlink()
    with TestClient(make_app()) as client:
        report = v.run_live(client, ENDPOINTS, api_fixtures)
    text = errors_of(report)
    assert "echo.request.json: text" in text
    assert any("file fixture missing" in reason for reason in report.blocked)


def test_validate_response(tmp_path):
    good = tmp_path / "echo.json"
    good.write_text('{"contract_version": "1.0", "text": "x"}', encoding="utf-8")
    assert v.validate_response("echo", good, ENDPOINTS).ok
    error = tmp_path / "error.json"
    error.write_text(api_error(ErrorCode.TIMEOUT, "slow").model_dump_json(), encoding="utf-8")
    assert v.validate_response("echo", error, ENDPOINTS).ok
    bad = tmp_path / "bad.json"
    bad.write_text('{"text": "x"}', encoding="utf-8")
    assert not v.validate_response("echo", bad, ENDPOINTS).ok
    with pytest.raises(v.ToolError):
        v.validate_response("nope", good, ENDPOINTS)


def test_missing_inputs_exit_2(api_fixtures, tmp_path):
    """D-052: a missing or unreadable input means the run could not complete, even with errors."""
    with pytest.raises(v.ToolError):
        v.validate_response("echo", tmp_path / "nope.json", ENDPOINTS)
    (api_fixtures / "echo.request.json").unlink()
    with TestClient(make_app(version=False)) as client:
        report = v.run_live(client, ENDPOINTS, api_fixtures)
    assert report.exit_code == 2
    assert any("request fixture missing" in reason for reason in report.blocked)
    assert "has no contract_version" in errors_of(report)  # still reported


def test_a_subject_that_is_not_utf8_exits_1(tmp_path):
    """D-055: the file under check was opened; bad encoding is its defect (exit 1, not 2)."""
    bad = tmp_path / "rarp.json"
    bad.write_bytes(b"\xff\xfe\x00not utf-8")
    assert v.validate_reference(bad).exit_code == 1
    assert v.validate_response("echo", bad, ENDPOINTS).exit_code == 1


def test_an_unreachable_brain_exits_2(api_fixtures):
    with v.httpx.Client(base_url="http://127.0.0.1:9", timeout=2) as client:
        report = v.run_live(client, ENDPOINTS, api_fixtures)
    assert report.exit_code == 2
    assert any("can't reach the Brain" in reason for reason in report.blocked)


def test_without_a_registry_the_api_checks_cannot_run(monkeypatch, tmp_path):
    def missing():
        raise v.ToolError("no registry")

    monkeypatch.setattr(v, "load_endpoints", missing)
    code, text = run(["response", "echo", str(tmp_path / "x.json")])
    assert code == 2 and "no registry" in text
