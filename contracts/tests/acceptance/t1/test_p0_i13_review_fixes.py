"""Dev1's `/code-review` fixes (4b7478f, brief criteria R1-R5) and the Team Lead's answer on issue
#13 (decisions 1-3, AC1-AC7; logged as D-064). Narrow re-test at 8e37499 (D-057).

Brief criteria (verbatim):
- R1 "A URI built by `media_fragment()` always validates as `MediaEvidence` with the same
  `t_start`/`t_end`, including values on a half millisecond (e.g. 2544.3105). The tolerance is half
  a millisecond, as before: `video.mp4#t=2280.001,...` against 2280.0 still fails."
- R2 "`scrubgpt-validate live`: each of these blocks the run (exit 2, CANNOT FINISH), never exit 1
  and never a traceback (D-055: a request fixture is an input, not the subject): a request fixture
  that fails its request model; a request fixture that isn't a JSON object; an unreadable file
  fixture."
- R3 "`scrubgpt-validate response`: only a JSON object with an `error` key is checked as an
  `ApiError`. A body that is a JSON string or a list is checked against the endpoint's response
  model (exit 1), never as `ApiError`."
- R4 "`validate case`: a question's `quote.text` is compared with its utterance's text after NFC on
  both sides. An NFD copy passes; a real difference in either half still fails (#9 AC5 unchanged)."
- R5 "`Utterance` accepts only `class` as the key. `class_` as a JSON key is a validation error.
  Dumps still write `class`."
#13 decisions: 1. a clip URI belongs to the evidence's own case; 2. `scrubgpt-validate case
--drop` (D-038); 3. groundings only on decision content (`GROUNDABLE_ROOTS`).
"""

from __future__ import annotations

import copy
import json
import os
import random
import shutil
import socket
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import MappingProxyType
from typing import Any, ClassVar

import pytest
from pydantic import TypeAdapter, ValidationError, model_validator
from scrubgpt_contracts.models import brain_api
from scrubgpt_contracts.models.case_package import Timeline, Utterance
from scrubgpt_contracts.models.common import Evidence, NonEmptyStr, VersionedModel, media_fragment
from scrubgpt_contracts.models.decision_record import (
    GROUNDABLE_ROOTS,
    DecisionRecord,
    DecisionRecordDraft,
)

CASE_ID = "case-fixture-01"
EVIDENCE = TypeAdapter(Evidence)
REPO = Path(__file__).resolve().parents[4]
FIXTURES_BRAIN_API = REPO / "contracts" / "fixtures" / "brain_api"


def _media(uri: str, t_start: float, t_end: float, case_id: str = CASE_ID) -> dict[str, Any]:
    return {"kind": "media", "case_id": case_id, "uri": uri, "t_start": t_start, "t_end": t_end}


def _draft(record: dict[str, Any]) -> dict[str, Any]:
    draft = copy.deepcopy(record)
    draft["id"] = None
    draft["provenance"]["confirmed_by"] = None
    draft["provenance"]["confirmed_at"] = None
    return draft


def _named(lines: list[str], *names: str) -> bool:
    return any(all(n in ln for n in names) for ln in lines)


# --- R1: media_fragment() output always validates ----------------------------------------------

HALF_MS = [2544.3105, 0.0005, 0.0015, 1.2345, 58.0005, 1234.5675, 2280.0005, 3599.9995, 7199.9985]


def _r1_values() -> list[float]:
    rng = random.Random(20261017)
    values = list(HALF_MS)
    values += [k + j / 2000 for k in (0, 1, 57, 2544, 3600) for j in range(1, 2000, 2)]  # x.xxx5
    values += [round(rng.uniform(0, 7200), rng.choice([0, 1, 3, 4, 6])) for _ in range(3000)]
    values += [rng.uniform(0, 7200) for _ in range(3000)]
    return values


@pytest.mark.parametrize("path", ["video.mp4", f"clips/{CASE_ID}.m01.mp4"])
def test_r1_media_fragment_output_always_validates_with_the_same_span(path):
    """R1: "A URI built by `media_fragment()` always validates as `MediaEvidence` with the same
    `t_start`/`t_end`, including values on a half millisecond (e.g. 2544.3105)" - for t_start and
    for t_end, over half-millisecond, rounded and arbitrary floats."""
    failed = []
    for t in _r1_values():
        for t_start, t_end in ((t, t + 20.0), (max(t - 20.0, 0.0), t), (t, t)):
            uri = media_fragment(path, t_start, t_end)
            try:
                EVIDENCE.validate_python(_media(uri, t_start, t_end))
            except ValidationError:
                failed.append((uri, t_start, t_end))
    assert not failed, f"{len(failed)} helper URIs rejected, e.g. {failed[:5]}"


@pytest.mark.parametrize(
    ("uri", "t_start", "t_end"),
    [
        ("video.mp4#t=2280.001,2300.0", 2280.0, 2300.0),
        ("video.mp4#t=2280.0,2300.001", 2280.0, 2300.0),
        ("video.mp4#t=2279.999,2300.0", 2280.0, 2300.0),
        ("video.mp4#t=2544.312,2564.3105", 2544.3105, 2564.3105),
    ],
    ids=repr,
)
def test_r1_tolerance_is_still_half_a_millisecond(uri, t_start, t_end):
    """R1: "The tolerance is half a millisecond, as before: `video.mp4#t=2280.001,...` against
    2280.0 still fails" (also on t_end, below, and next to a half-millisecond value)."""
    with pytest.raises(ValidationError):
        EVIDENCE.validate_python(_media(uri, t_start, t_end))


# --- R2: `validate live` with a broken request fixture blocks the run (exit 2) -------------------


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _stop(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
    else:
        proc.terminate()
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)


@pytest.fixture(scope="module")
def brain_url(tmp_path_factory) -> Iterator[str]:
    """The fake Brain (`scrubgpt-mock-brain`) on a free local port, so the only thing that can
    block `live` is the request fixture under test."""
    port = _free_port()
    log = tmp_path_factory.mktemp("r2-fake-brain") / "fake-brain.log"
    uv = shutil.which("uv")
    command = [uv, "run", "--frozen", "--no-sync"] if uv else []
    command += ["scrubgpt-mock-brain", "--port", str(port), "--host", "127.0.0.1"]
    with log.open("wb") as sink:
        proc = subprocess.Popen(command, cwd=REPO, stdout=sink, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 90
        while True:
            if proc.poll() is not None:
                pytest.fail(f"fake Brain exited early:\n{log.read_text(errors='replace')}")
            try:
                with urllib.request.urlopen(url + "/health", timeout=2) as resp:
                    if resp.status == 200:
                        break
            except (urllib.error.URLError, OSError):
                pass
            if time.monotonic() > deadline:
                pytest.fail(f"fake Brain not up after 90 s:\n{log.read_text(errors='replace')}")
            time.sleep(0.3)
        yield url
    finally:
        _stop(proc)


@pytest.fixture
def request_fixtures(tmp_path) -> Path:
    target = tmp_path / "brain_api"
    shutil.copytree(FIXTURES_BRAIN_API, target)
    return target


def _live(run_validate, url: str, fixtures: Path):
    return run_validate("live", "--base-url", url, "--fixtures", fixtures, "--timeout", "60")


def _assert_blocked(result, *names: str) -> None:
    assert result.code == 2, result.output
    assert "CANNOT FINISH" in result.output, result.output
    assert "Traceback" not in result.output, result.output
    not_run = [ln for ln in result.output.splitlines() if "NOT RUN" in ln]
    assert not_run, result.output
    for name in names:
        assert any(name in ln for ln in not_run), result.output


@contextmanager
def _os_unreadable(path: Path) -> Iterator[None]:
    """`path` exists but the OS refuses to read it (a byte-range lock on Windows, mode 0
    elsewhere)."""
    if sys.platform == "win32":
        import msvcrt

        size = 1 << 20
        fd = os.open(path, os.O_RDWR)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, size)
        try:
            with pytest.raises(PermissionError):
                path.read_bytes()
            yield
        finally:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, size)
            os.close(fd)
    else:
        mode = path.stat().st_mode
        path.chmod(0)
        try:
            try:
                path.read_bytes()
            except PermissionError:
                pass
            else:
                pytest.skip("file permissions are not enforced for this user")
            yield
        finally:
            path.chmod(mode)


def test_r2_control_live_with_the_fixture_copy_exits_0(brain_url, request_fixtures, run_validate):
    """R2 control: the unchanged copy of the request fixtures passes against the fake Brain."""
    result = _live(run_validate, brain_url, request_fixtures)
    assert result.code == 0, result.output


@pytest.mark.parametrize(
    ("name", "body"),
    [
        ("translate", {"texts": []}),
        ("translate", {"texts": [{"text": "", "from_lang": "ja"}]}),
        ("translate", {"wrong": 1}),
        ("embed", {}),
        ("extract", {"question": None}),
    ],
    ids=["translate-empty-list", "translate-empty-text", "translate-wrong-key", "embed", "extract"],
)
def test_r2_request_fixture_failing_its_model_blocks_the_run(
    brain_url, request_fixtures, run_validate, name, body
):
    """R2: "a request fixture that fails its request model" -> exit 2, CANNOT FINISH, never 1,
    no traceback (D-055: the request fixture is an input)."""
    (request_fixtures / f"{name}.request.json").write_text(json.dumps(body), encoding="utf-8")
    _assert_blocked(_live(run_validate, brain_url, request_fixtures), name)


@pytest.mark.parametrize(
    "text", ['["a", "b"]', '"just a string"', "42", "null", "true"], ids=lambda t: t[:8]
)
def test_r2_request_fixture_that_is_not_an_object_blocks_the_run(
    brain_url, request_fixtures, run_validate, text
):
    """R2: "a request fixture that isn't a JSON object" -> exit 2, CANNOT FINISH."""
    (request_fixtures / "translate.request.json").write_text(text, encoding="utf-8")
    _assert_blocked(_live(run_validate, brain_url, request_fixtures), "translate")


def test_r2_unreadable_file_fixture_blocks_the_run(brain_url, request_fixtures, run_validate):
    """R2: "an unreadable file fixture" (the `/transcribe` audio upload, refused by the OS) ->
    exit 2, CANNOT FINISH."""
    audio = sorted(request_fixtures.glob("transcribe.request.audio.*"))
    assert audio, list(request_fixtures.iterdir())
    with _os_unreadable(audio[0]):
        result = _live(run_validate, brain_url, request_fixtures)
    _assert_blocked(result, "transcribe")


def test_r2_file_fixture_that_is_a_folder_blocks_the_run(brain_url, request_fixtures, run_validate):
    """R2 "an unreadable file fixture", second form: a folder where the audio file should be."""
    audio = sorted(request_fixtures.glob("transcribe.request.audio.*"))[0]
    audio.unlink()
    audio.mkdir()
    _assert_blocked(_live(run_validate, brain_url, request_fixtures), "transcribe")


def test_r2_cli_blocked_run_prints_no_traceback(brain_url, request_fixtures):
    """R2 "never a traceback", through the installed console script."""
    (request_fixtures / "translate.request.json").write_text("[1, 2]", encoding="utf-8")
    exe = shutil.which("scrubgpt-validate")
    assert exe
    proc = subprocess.run(
        [exe, "live", "--base-url", brain_url, "--fixtures", str(request_fixtures)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "Traceback" not in proc.stdout + proc.stderr, proc.stdout + proc.stderr


# --- R3: only an object with `error` is an ApiError --------------------------------------------


class SpyResponse(VersionedModel):
    """A stand-in response model that records every body it is asked to validate."""

    status: NonEmptyStr
    seen: ClassVar[list[Any]] = []

    @model_validator(mode="before")
    @classmethod
    def _record(cls, data: Any) -> Any:
        SpyResponse.seen.append(data)
        return data


@pytest.fixture
def spy_endpoint(monkeypatch) -> str:
    """The `ENDPOINTS` registry (D-037) with one stand-in endpoint answering `SpyResponse`."""
    SpyResponse.seen = []
    endpoint = brain_api.Endpoint(
        method="GET", path="/spy", request=None, response=SpyResponse, files=(), timeout_s=5.0
    )
    monkeypatch.setattr(brain_api, "ENDPOINTS", MappingProxyType({"spy": endpoint}))
    return "spy"


API_ERROR = {
    "contract_version": "1.0",
    "error": {"code": "bad_request", "message": "x", "retryable": False},
}


@pytest.mark.parametrize(
    "body",
    ["error", ["error"], [API_ERROR], [{"error": "x"}], []],
    ids=[
        "string-error",
        "list-of-string",
        "list-of-api-error",
        "list-of-error-object",
        "empty-list",
    ],
)
def test_r3_string_or_list_body_is_checked_against_the_response_model(
    spy_endpoint, tmp_path, run_validate, body
):
    """R3: "A body that is a JSON string or a list is checked against the endpoint's response
    model (exit 1), never as `ApiError`" - the endpoint's model receives the body, and the run
    exits 1 without reporting it as an `ApiError`."""
    path = tmp_path / "body.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    result = run_validate("response", spy_endpoint, path)
    assert result.code == 1, result.output
    assert body in SpyResponse.seen, (SpyResponse.seen, result.output)
    assert "as ApiError" not in result.output, result.output


@pytest.mark.parametrize("body", [API_ERROR, {"error": "boom"}], ids=["valid", "invalid"])
def test_r3_object_with_error_key_is_checked_as_api_error(
    spy_endpoint, tmp_path, run_validate, body
):
    """R3: "only a JSON object with an `error` key is checked as an `ApiError`": the endpoint's
    model never sees it; a valid ApiError passes (exit 0), an invalid one fails (exit 1)."""
    path = tmp_path / "body.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    result = run_validate("response", spy_endpoint, path)
    assert SpyResponse.seen == [], SpyResponse.seen
    if body is API_ERROR:
        assert result.code == 0, result.output
        assert "as ApiError" in result.output, result.output
    else:
        assert result.code == 1, result.output


def test_r3_object_without_error_key_uses_the_response_model(spy_endpoint, tmp_path, run_validate):
    """R3 control: an object without `error` goes to the endpoint's model (exit 0 when valid)."""
    body = {"contract_version": "1.0", "status": "ok"}
    path = tmp_path / "body.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    result = run_validate("response", spy_endpoint, path)
    assert result.code == 0, result.output
    assert body in SpyResponse.seen


@pytest.mark.parametrize("endpoint", sorted(brain_api.ENDPOINTS))
@pytest.mark.parametrize("body", ['"error"', '["error"]'], ids=["string", "list"])
def test_r3_real_endpoints_reject_string_and_list_bodies(tmp_path, run_validate, endpoint, body):
    """R3 with the real registry: a JSON string or list body is exit 1 for every endpoint."""
    path = tmp_path / "body.json"
    path.write_text(body, encoding="utf-8")
    result = run_validate("response", endpoint, path)
    assert result.code == 1, result.output
    assert "as ApiError" not in result.output


# --- R4: question quotes compared after NFC -------------------------------------------------------


def _quote_case(data_dir, *, quote_ja=None, utter_ja=None, quote_en=None, utter_en=None):
    questions = data_dir.load("questions.json")
    q = next(x for x in questions["operating"] if x["id"] == f"{CASE_ID}.m01.q2")
    timeline = data_dir.load("timeline.json")
    u = next(x for x in timeline["utterances"] if x["id"] == q["quote"]["utterance_id"])
    for target, half, value in (
        (q["quote"]["text"], "ja", quote_ja),
        (u["text"], "ja", utter_ja),
        (q["quote"]["text"], "en", quote_en),
        (u["text"], "en", utter_en),
    ):
        if value is not None:
            target[half] = value(target[half]) if callable(value) else value
    data_dir.save("questions.json", questions)
    data_dir.save("timeline.json", timeline)
    return q["id"]


def _nfd(text: str) -> str:
    out = unicodedata.normalize("NFD", text)
    assert out != text, f"{text!r} has nothing to decompose"
    return out


EN_NFC = "Raise the pressure, café."


@pytest.mark.parametrize(
    "edit",
    [
        {"quote_ja": _nfd},
        {"utter_ja": _nfd},
        {"quote_en": _nfd(EN_NFC), "utter_en": EN_NFC},
        {"quote_en": EN_NFC, "utter_en": _nfd(EN_NFC)},
    ],
    ids=["quote-ja-nfd", "utterance-ja-nfd", "quote-en-nfd", "utterance-en-nfd"],
)
def test_r4_nfd_copy_of_the_quote_passes(data_dir, run_validate, edit):
    """R4: "a question's `quote.text` is compared with its utterance's text after NFC on both
    sides. An NFD copy passes" (either side, either half; u0003's げ/だ, and é)."""
    _quote_case(data_dir, **edit)
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 0, result.output


@pytest.mark.parametrize(
    "edit",
    [
        {"quote_ja": lambda s: _nfd(s.replace("少し", "大量に"))},
        {"quote_en": _nfd("Raise the pressure, caf\u00e9!"), "utter_en": EN_NFC},
        {"quote_ja": lambda s: unicodedata.normalize("NFKD", s.replace("。", "．"))},
    ],
    ids=["ja-nfd-but-different", "en-nfd-but-different", "nfkd-fullwidth-stop"],
)
def test_r4_real_difference_still_fails(data_dir, run_validate, edit):
    """R4: "a real difference in either half still fails (#9 AC5 unchanged)" - also when the
    differing text is NFD-encoded; nothing beyond NFC is normalised."""
    qid = _quote_case(data_dir, **edit)
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 1, result.output
    assert any(qid in ln for ln in result.error_lines), result.output


# --- R5: `class` only --------------------------------------------------------------------------


def _utterance_doc(docs) -> dict[str, Any]:
    return copy.deepcopy(docs["timeline.json"]["utterances"][0])


def test_r5_class_key_is_accepted_and_dumped_as_class(docs):
    """R5: "`Utterance` accepts ... `class` as the key ... Dumps still write `class`" (D-049)."""
    raw = _utterance_doc(docs)
    for parsed in (
        Utterance.model_validate(raw),
        Utterance.model_validate_json(json.dumps(raw, ensure_ascii=False)),
    ):
        for dumped in (
            parsed.model_dump(mode="json"),
            parsed.model_dump(),
            json.loads(parsed.model_dump_json()),
        ):
            assert dumped["class"] == raw["class"], dumped
            assert "class_" not in dumped, dumped


def test_r5_class_underscore_key_is_a_validation_error(docs):
    """R5: "`class_` as a JSON key is a validation error" (dict and JSON input)."""
    raw = _utterance_doc(docs)
    raw["class_"] = raw.pop("class")
    with pytest.raises(ValidationError):
        Utterance.model_validate(raw)
    with pytest.raises(ValidationError):
        Utterance.model_validate_json(json.dumps(raw, ensure_ascii=False))
    with pytest.raises(ValidationError):
        Utterance(**raw)


def test_r5_timeline_with_class_underscore_fails_and_round_trips_class(
    docs, data_dir, run_validate
):
    """R5 in `timeline.json`: an utterance written with `class_` fails the `Timeline` model and
    `validate case` (exit 1, naming timeline.json); the fixture timeline dumps `class` back."""
    timeline = copy.deepcopy(docs["timeline.json"])
    dumped = json.loads(Timeline.model_validate(timeline).model_dump_json())
    assert [u["class"] for u in dumped["utterances"]] == [
        u["class"] for u in timeline["utterances"]
    ]
    timeline["utterances"][0]["class_"] = timeline["utterances"][0].pop("class")
    with pytest.raises(ValidationError):
        Timeline.model_validate(timeline)
    data_dir.save("timeline.json", timeline)
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 1, result.output
    assert any("timeline.json" in ln for ln in result.error_lines), result.output


# --- #13 AC1, AC2: a clip URI belongs to the evidence's own case --------------------------------


def test_13ac1_clip_of_own_case_valid_other_case_invalid():
    """#13 AC1: "`MediaEvidence` with `case_id: case-fixture-01` and `uri:
    clips/case-fixture-01.m01.mp4#t=0,5` is valid. With `uri: clips/grasp-01.m07.mp4#t=0,5` it is
    a validation error.\""""
    EVIDENCE.validate_python(_media(f"clips/{CASE_ID}.m01.mp4#t=0,5", 58.0, 78.0))
    EVIDENCE.validate_json(json.dumps(_media(f"clips/{CASE_ID}.m01.mp4#t=0,5", 58.0, 78.0)))
    with pytest.raises(ValidationError):
        EVIDENCE.validate_python(_media("clips/grasp-01.m07.mp4#t=0,5", 58.0, 78.0))
    with pytest.raises(ValidationError):
        EVIDENCE.validate_json(json.dumps(_media("clips/grasp-01.m07.mp4#t=0,5", 58.0, 78.0)))


@pytest.mark.parametrize(
    ("case_id", "moment_case"),
    [(CASE_ID, f"{CASE_ID}0"), (CASE_ID, "case-fixture"), (f"{CASE_ID}0", CASE_ID)],
)
def test_13ac1_prefix_must_be_the_case_id_plus_dot(case_id, moment_case):
    """#13 decision 1: "the `<moment_id>` must start with the evidence's own `case_id + "."`" -
    a case id that merely shares a text prefix doesn't count."""
    with pytest.raises(ValidationError):
        EVIDENCE.validate_python(_media(f"clips/{moment_case}.m01.mp4#t=0,5", 1.0, 2.0, case_id))


@pytest.mark.parametrize("case_id", [CASE_ID, "grasp-01", "yt-en-03"])
def test_13ac2_video_mp4_is_not_affected(case_id):
    """#13 AC2: "`uri: video.mp4#...` is not affected by criterion 1" (any case's evidence)."""
    EVIDENCE.validate_python(_media("video.mp4#t=58.0,78.0", 58.0, 78.0, case_id))


@pytest.mark.parametrize("model", [DecisionRecord, DecisionRecordDraft], ids=lambda m: m.__name__)
def test_13ac2_record_or_draft_citing_another_cases_clip_fails(docs, model):
    """#13 AC2: "A `DecisionRecord` or `DecisionRecordDraft` whose clip evidence names another
    case's moment fails validation" (and its own case's clip passes)."""
    record = copy.deepcopy(docs["seed_records.json"]["records"][0])
    doc = _draft(record) if model is DecisionRecordDraft else record
    doc["evidence"][0]["uri"] = f"clips/{CASE_ID}.m01.mp4#t=0,5"
    model.model_validate(doc)
    doc["evidence"][0]["uri"] = "clips/grasp-01.m07.mp4#t=0,5"
    with pytest.raises(ValidationError):
        model.model_validate(doc)
    with pytest.raises(ValidationError):
        model.model_validate_json(json.dumps(doc, ensure_ascii=False))


# --- #13 AC3-AC5: `validate case --drop` ----------------------------------------------------------


def test_13ac3_missing_video_exits_1_without_drop(data_dir, run_validate):
    """#13 AC3: "A copy of the fixture package with `video.mp4` removed: `validate case` exits 1
    and names the missing file"."""
    (data_dir.case_dir / "video.mp4").unlink()
    result = run_validate("case", data_dir.case_dir)
    assert result.code == 1, result.output
    assert any("video.mp4" in ln for ln in result.error_lines), result.output


def test_13ac3_missing_video_with_drop_exits_0_with_a_warning(data_dir, run_validate):
    """#13 AC3: "`validate case --drop` exits 0 and prints a warning about the missing
    `video.mp4`" (decision 2: the seed evidence on `video.mp4` isn't checked for the file)."""
    (data_dir.case_dir / "video.mp4").unlink()
    result = run_validate("case", "--drop", data_dir.case_dir)
    assert result.code == 0, result.output
    assert result.counts[0] == 0, result.output
    assert any("video.mp4" in ln for ln in result.warning_lines), result.output


def test_13ac3_drop_option_after_the_folder_works_too(data_dir, run_validate):
    """#13 AC3 with the option written after the folder (`case <dir> --drop`)."""
    (data_dir.case_dir / "video.mp4").unlink()
    result = run_validate("case", data_dir.case_dir, "--drop")
    assert result.code == 0, result.output
    assert any("video.mp4" in ln for ln in result.warning_lines), result.output


@pytest.mark.parametrize("video", ["absent", "present"])
@pytest.mark.parametrize(
    "remove", ["poster.jpg", f"clips/{CASE_ID}.m01.mp4", f"clips/{CASE_ID}.m03.jpg"]
)
def test_13ac4_drop_still_requires_poster_and_clips(data_dir, run_validate, remove, video):
    """#13 AC4: "With `--drop`, removing `poster.jpg`, or a clip that a moment needs, still exits
    1" (named in an error), with or without `video.mp4`."""
    if video == "absent":
        (data_dir.case_dir / "video.mp4").unlink()
    (data_dir.case_dir / remove).unlink()
    result = run_validate("case", "--drop", data_dir.case_dir)
    assert result.code == 1, result.output
    assert any(Path(remove).name in ln for ln in result.error_lines), result.output


@pytest.mark.parametrize("video", ["absent", "present"])
def test_13ac4_drop_still_checks_the_video_fragment(data_dir, run_validate, video):
    """#13 AC4: "A seed `video.mp4` fragment that differs from `t_start`/`t_end` still exits 1"
    (decision 2: "The fragment and `t_start`/`t_end` checks (D-058) still run")."""
    if video == "absent":
        (data_dir.case_dir / "video.mp4").unlink()
    seeds = data_dir.load("seed_records.json")
    seeds["records"][0]["evidence"][0]["uri"] = "video.mp4#t=250.0,290.0"
    data_dir.save("seed_records.json", seeds)
    result = run_validate("case", "--drop", data_dir.case_dir)
    assert result.code == 1, result.output
    assert any("seed_records.json" in ln for ln in result.error_lines), result.output


@pytest.mark.parametrize("how", ["lookup", "--reference"])
def test_13ac4_drop_with_a_missing_reference_exits_2(data_dir, run_validate, tmp_path, how):
    """#13 AC4: "A missing reference still exits 2" (D-055), in a drop without `video.mp4`."""
    (data_dir.case_dir / "video.mp4").unlink()
    args = ["case", "--drop", data_dir.case_dir]
    if how == "lookup":
        data_dir.reference.unlink()
    else:
        args += ["--reference", tmp_path / "nowhere" / "rarp.json"]
    result = run_validate(*args)
    assert result.code == 2, result.output


def test_13ac5_drop_on_the_complete_package_is_the_same_as_without(data_dir, run_validate):
    """#13 AC5: "With `--drop`, the complete fixture package (with `video.mp4`) gives the same
    result as without `--drop` (exit 0)" - same code, same error and warning counts."""
    plain = run_validate("case", data_dir.case_dir)
    drop = run_validate("case", "--drop", data_dir.case_dir)
    assert plain.code == drop.code == 0, plain.output + "\n" + drop.output
    assert plain.counts == drop.counts == (0, 0), drop.output


# --- #13 AC6, AC7: groundings only on decision content --------------------------------------------

ROOTS_13 = {
    "context",
    "situation_cue",
    "obstacle",
    "anticipation",
    "action",
    "alternatives",
    "reason",
    "immediate_result",
    "delayed_outcome",
    "kind",
    "new_terms",
}

METADATA = [
    "id",
    "case_id",
    "step_id",
    "confidence",
    "provenance",
    "provenance.trust_label",
    "evidence[0]",
    "grounding[0]",
    "language",
    "contract_version",
    # deeper paths that still start at metadata
    "provenance.generated_by.model",
    "evidence[0].uri",
    "grounding[0].quote",
]

MODELS = [
    pytest.param(DecisionRecord, id="DecisionRecord"),
    pytest.param(DecisionRecordDraft, id="DecisionRecordDraft"),
]


def _as(model, record: dict[str, Any]) -> dict[str, Any]:
    return _draft(record) if model is DecisionRecordDraft else copy.deepcopy(record)


def _grounded(doc: dict[str, Any], field: str) -> dict[str, Any]:
    doc = copy.deepcopy(doc)
    doc["grounding"].append({"field": field, "quote": "静脈性", "source": "answer"})
    return doc


def test_13_groundable_roots_are_the_eleven_content_fields():
    """#13 decision 3: "A `grounding[].field` must start at one of these top-level fields:
    `context`, `situation_cue`, `obstacle`, `anticipation`, `action`, `alternatives`, `reason`,
    `immediate_result`, `delayed_outcome`, `kind`, `new_terms`" (`GROUNDABLE_ROOTS`)."""
    assert set(GROUNDABLE_ROOTS) == ROOTS_13


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("field", METADATA)
def test_13ac6_grounding_on_metadata_is_an_error(docs, model, field):
    """#13 AC6: "A grounding on `id`, `case_id`, `step_id`, `confidence`, `provenance`,
    `provenance.trust_label`, `evidence[0]`, `grounding[0]`, `language` or `contract_version` is a
    validation error in both models"."""
    doc = _as(model, docs["seed_records.json"]["records"][0])
    model.model_validate(doc)
    with pytest.raises(ValidationError):
        model.model_validate(_grounded(doc, field))
    with pytest.raises(ValidationError):
        model.model_validate_json(json.dumps(_grounded(doc, field), ensure_ascii=False))


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("field", ["moment_id", "question_id"])
def test_13ac6_moment_id_and_question_id_are_errors_when_non_null(docs, model, field):
    """#13 AC6: "`moment_id` and `question_id` are errors too when non-null" (record 0 is on m01;
    its `question_id` is set to m01's `q1`)."""
    doc = _as(model, docs["seed_records.json"]["records"][0])
    assert doc["moment_id"] == f"{CASE_ID}.m01"
    doc["question_id"] = f"{CASE_ID}.m01.q1"
    model.model_validate(doc)
    with pytest.raises(ValidationError):
        model.model_validate(_grounded(doc, field))


CONTENT = [
    "action.type",
    "action.actor",
    "kind",
    "delayed_outcome",
    "situation_cue.cue_terms[0]",
    "context",
    "alternatives[0]",
    "situation_cue",
    "action",
    "obstacle",
    "obstacle.family",
    "new_terms[0]",
]


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("field", CONTENT)
def test_13ac7_grounding_on_content_stays_valid(docs, model, field):
    """#13 AC7: "A grounding on `action.type`, `action.actor`, `kind`, `delayed_outcome`,
    `situation_cue.cue_terms[0]` (when non-empty), `context` or `alternatives[0]` stays valid when
    the value exists and is non-null" (cue_terms and new_terms are filled first)."""
    doc = _as(model, docs["seed_records.json"]["records"][0])
    doc["situation_cue"]["cue_terms"] = ["にじみ"]
    doc["new_terms"] = [{"term": "にじみ", "lang": "ja"}]
    assert doc["alternatives"] and doc["obstacle"] is not None
    model.model_validate(_grounded(doc, field))
    model.model_validate_json(json.dumps(_grounded(doc, field), ensure_ascii=False))


def test_13ac7_every_fixture_grounding_still_validates(docs):
    """#13 AC7: "All grounding fields in the existing fixtures still validate" (every seed record,
    as a record and as a draft), and each starts at a content root."""
    from scrubgpt_contracts.models.case_package import SeedRecords

    SeedRecords.model_validate(docs["seed_records.json"])
    for record in docs["seed_records.json"]["records"]:
        DecisionRecord.model_validate(record)
        DecisionRecordDraft.model_validate(_draft(record))
        for g in record["grounding"]:
            root = g["field"].split(".")[0].split("[")[0]
            assert root in ROOTS_13, (record["id"], g["field"])
