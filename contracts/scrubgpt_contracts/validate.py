"""`scrubgpt-validate`: check files and a running Brain against the contracts (plan §4.5).

    scrubgpt-validate case <dir> [--reference <file>]
    scrubgpt-validate reference <file>
    scrubgpt-validate response <endpoint> <file>
    scrubgpt-validate live --base-url <url> [--fixtures <dir>] [--timeout <s>]

Exit code 0 = no errors (warnings allowed), 1 = errors, 2 = the check could not run.

Python API (e.g. for the app's loader in drop mode, D-038): `load_case()` parses each file on its
own, `validate_case()` adds the checks across files, `validate_reference()`, `validate_response()`
and `run_live()`.

`response` and `live` use Dev2's `ENDPOINTS` registry in `models/brain_api.py`: a mapping from
endpoint name to an object with `method` (`GET`/`POST`), `path`, `request` (model or `None`),
`response` (model) and, for multipart endpoints, `files` (names of the file fields). Request
fixtures are `fixtures/brain_api/<name>.request.json` (form fields for multipart endpoints) and
`<name>.request.<file field>.<ext>` for each file field.
"""

import argparse
import json
import mimetypes
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ValidationError

from scrubgpt_contracts.models.case_package import (
    JSON_FILES,
    REQUIRED_FILES,
    Case,
    CaseSource,
    Metrics,
    Moments,
    Questions,
    SeedRecords,
    Timeline,
)
from scrubgpt_contracts.models.common import (
    CONTRACT_VERSION,
    ApiError,
    ErrorCode,
    MediaEvidence,
    TranscriptEvidence,
    VersionedModel,
)
from scrubgpt_contracts.models.decision_record import DecisionRecord, ungrounded_fields
from scrubgpt_contracts.models.reference import ProcedureReference

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
TIME_TOLERANCE_S = 1e-6
VIDEO_DURATION_TOLERANCE_S = 1.0

Level = Literal["error", "warning"]


class ToolError(Exception):
    """The check could not run (exit code 2)."""


@dataclass
class Issue:
    level: Level
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.level.upper():7} {self.where}: {self.message}"


@dataclass
class Report:
    """The result of one check: what was checked and every issue found."""

    target: str
    checked: list[str] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)

    def error(self, where: str, message: str) -> None:
        self.issues.append(Issue("error", where, message))

    def warn(self, where: str, message: str) -> None:
        self.issues.append(Issue("warning", where, message))

    @property
    def errors(self) -> list[Issue]:
        return [issue for issue in self.issues if issue.level == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [issue for issue in self.issues if issue.level == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def render(self) -> str:
        lines = [f"scrubgpt-validate: {self.target}"]
        lines += [f"  checked {item}" for item in self.checked]
        lines += [f"  {issue}" for issue in self.issues]
        verdict = "PASS" if self.ok else "FAIL"
        lines.append(f"{verdict}: {len(self.errors)} error(s), {len(self.warnings)} warning(s)")
        return "\n".join(lines)


def _path_of(loc: Iterable[int | str]) -> str:
    text = ""
    for part in loc:
        text += f"[{part}]" if isinstance(part, int) else (f".{part}" if text else str(part))
    return text or "(document)"


def _validation_messages(exc: ValidationError) -> list[str]:
    messages = []
    for err in exc.errors(include_url=False):
        message = err["msg"].removeprefix("Value error, ")
        value = err.get("input")
        if isinstance(value, str | int | float | bool) and len(repr(value)) <= 60:
            message += f" (got {value!r})"
        messages.append(f"{_path_of(err['loc'])}: {message}")
    return messages


def _parse[M: BaseModel](model: type[M], text: str | bytes, where: str, report: Report) -> M | None:
    try:
        return model.model_validate_json(text)
    except ValidationError as exc:
        for message in _validation_messages(exc):
            report.error(where, message)
        return None


def _read(path: Path, report: Report) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        report.error(path.name, f"can't read: {exc}")
    except UnicodeDecodeError:
        report.error(path.name, "not UTF-8 text")
    return None


# ── Case Package ──────────────────────────────────────────────────────────────


@dataclass
class CaseLoad:
    """Each file of a case package, parsed on its own (`None` = missing or invalid)."""

    case_dir: Path
    report: Report
    documents: dict[str, VersionedModel | None] = field(default_factory=dict)

    def get[M: VersionedModel](self, name: str, model: type[M]) -> M | None:
        document = self.documents.get(name)
        return document if isinstance(document, model) else None

    def file_ok(self, name: str) -> bool:
        """True if the file is present and valid on its own."""
        return self.documents.get(name) is not None


def load_case(case_dir: Path) -> CaseLoad:
    """Parse every JSON file of a package on its own, and report missing required files."""
    report = Report(f"case {case_dir}")
    load = CaseLoad(case_dir, report)
    if not case_dir.is_dir():
        raise ToolError(f"not a folder: {case_dir}")
    for name in REQUIRED_FILES:
        target = case_dir / name.rstrip("/")
        present = target.is_dir() if name.endswith("/") else target.is_file()
        if not present:
            report.error(name, "required file is missing (the package is incomplete)")
    for name, model in JSON_FILES.items():
        path = case_dir / name
        if not path.is_file():
            load.documents[name] = None
            continue
        text = _read(path, report)
        load.documents[name] = None if text is None else _parse(model, text, name, report)
        if load.documents[name] is not None:
            report.checked.append(name)
    return load


def _find_reference(load: CaseLoad, step_ids: set[str], override: Path | None) -> Path | None:
    if override is not None:
        return override
    prefixes = {step_id.split(".", 1)[0] for step_id in step_ids}
    if len(prefixes) > 1:
        load.report.error("cross-file", f"step ids from several procedures: {sorted(prefixes)}")
        return None
    if not prefixes:
        load.report.warn("cross-file", "no step ids, so the Procedure Reference isn't checked")
        return None
    return load.case_dir.resolve().parent.parent / "reference" / f"{prefixes.pop()}.json"


def _check_reference_ids(
    report: Report,
    reference: ProcedureReference,
    timeline: Timeline | None,
    moments: Moments | None,
    records: list[DecisionRecord],
    metrics: Metrics | None,
) -> None:
    steps = {step.id for step in reference.steps()}
    checkpoints = reference.checkpoint_ids()
    leaves = reference.leaf_ids()

    def need(ids: Iterable[str | None], known: set[str], where: str, what: str) -> None:
        for item_id in ids:
            if item_id is not None and item_id not in known:
                report.error(where, f"{what} {item_id} is not in the Procedure Reference")

    if timeline is not None:
        need((s.step_id for s in timeline.steps), steps, "timeline.json", "step")
    if moments is not None:
        need((m.step_id for m in moments.moments), steps, "moments.json", "step")
        need((m.checkpoint_id for m in moments.moments), checkpoints, "moments.json", "checkpoint")
        need((m.draft_obstacle for m in moments.moments), leaves, "moments.json", "obstacle")
    need((r.step_id for r in records), steps, "seed_records.json", "step")
    obstacles = (r.obstacle.type for r in records if r.obstacle is not None)
    need(obstacles, leaves, "seed_records.json", "obstacle")
    if metrics is not None:
        need((s.step_id for s in metrics.per_step), steps, "metrics.json", "step")


def _probe_duration(path: Path) -> float | None:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        return None
    command = [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0"]
    try:
        result = subprocess.run(
            [*command, str(path)], capture_output=True, text=True, timeout=60, check=True
        )
        return float(result.stdout.strip())
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def validate_case(case_dir: Path, reference_path: Path | None = None) -> Report:
    """Every check for one case package: each file, then the checks across files."""
    load = load_case(case_dir)
    report = load.report
    case = load.get("case.json", Case)
    timeline = load.get("timeline.json", Timeline)
    moments = load.get("moments.json", Moments)
    questions = load.get("questions.json", Questions)
    seed = load.get("seed_records.json", SeedRecords)
    metrics = load.get("metrics.json", Metrics)
    records = seed.records if seed is not None else []
    where = "cross-file"

    # Identity: the folder, case.json and every other file name the same case.
    if case is not None:
        if case.id != case_dir.resolve().name:
            report.error("case.json", f"id {case.id} doesn't match the folder {case_dir.name}")
        for name, document in load.documents.items():
            case_id = getattr(document, "case_id", None)
            if case_id is not None and case_id != case.id:
                report.error(name, f"case_id {case_id} doesn't match case.json ({case.id})")
        if case.source is CaseSource.YOUTUBE and case.source_url is None:
            report.warn("case.json", "a YouTube case has no source_url")
        if case.source is CaseSource.GRASP and metrics is None:
            report.warn("metrics.json", "a GraSP case has no valid metrics.json (C7)")

    # The Procedure Reference.
    step_ids = {s.step_id for s in timeline.steps} if timeline is not None else set()
    step_ids |= {m.step_id for m in moments.moments} if moments is not None else set()
    step_ids |= {r.step_id for r in records}
    ref_path = _find_reference(load, step_ids, reference_path)
    if ref_path is not None:
        if not ref_path.is_file():
            report.error(where, f"Procedure Reference not found: {ref_path} (use --reference)")
        else:
            text = _read(ref_path, report)
            reference = (
                None
                if text is None
                else _parse(ProcedureReference, text, f"reference {ref_path.name}", report)
            )
            if reference is not None:
                report.checked.append(f"against {ref_path}")
                _check_reference_ids(report, reference, timeline, moments, records, metrics)

    # Times stay within the video.
    if case is not None:
        spans: list[tuple[str, str, float]] = []
        if timeline is not None:
            for items in (
                timeline.steps,
                timeline.events,
                timeline.instruments,
                timeline.utterances,
            ):
                spans += [("timeline.json", item.id, item.t_end) for item in items]
        if moments is not None:
            spans += [("moments.json", m.id, m.t_end) for m in moments.moments]
        for record in records:
            for item in record.evidence:
                if isinstance(item, MediaEvidence):
                    spans.append(("seed_records.json", f"record {record.id} evidence", item.t_end))
        for name, item_id, t_end in spans:
            if t_end > case.duration_s + TIME_TOLERANCE_S:
                report.error(
                    name, f"{item_id} ends at {t_end} s, after the video ({case.duration_s} s)"
                )
        video = case_dir / "video.mp4"
        duration = _probe_duration(video) if video.is_file() else None
        if duration is not None and abs(duration - case.duration_s) > VIDEO_DURATION_TOLERANCE_S:
            report.warn("video.mp4", f"lasts {duration:.2f} s, but duration_s is {case.duration_s}")

    # Timeline: what other files point to.
    utterance_ids = {u.id for u in timeline.utterances} if timeline is not None else None
    if timeline is not None:
        tracks = {s.track for s in timeline.steps}
        if case is not None and timeline.steps and case.default_step_track not in tracks:
            report.warn("timeline.json", f"no steps on the default track {case.default_step_track}")
        for track in tracks:
            segments = sorted(
                (s for s in timeline.steps if s.track is track), key=lambda s: s.t_start
            )
            for before, after in zip(segments, segments[1:], strict=False):
                if after.t_start < before.t_end - TIME_TOLERANCE_S:
                    report.warn(
                        "timeline.json", f"{before.id} and {after.id} overlap ({track} track)"
                    )

    # Moments: clips and posters exist; ranked by score.
    moment_ids = {m.id for m in moments.moments} if moments is not None else None
    if moments is not None:
        for moment in moments.moments:
            for path in (moment.clip, moment.poster):
                if not (case_dir / path).is_file():
                    report.error("moments.json", f"{moment.id}: {path} is missing")
        scores = [m.score for m in moments.moments]
        if any(a < b for a, b in zip(scores, scores[1:], strict=False)):
            report.warn("moments.json", "moments are not in descending score order (rank = order)")
        clips = case_dir / "clips"
        expected = {Path(m.clip).name for m in moments.moments} | {
            Path(m.poster).name for m in moments.moments
        }
        if clips.is_dir():
            for extra in sorted(p.name for p in clips.iterdir() if p.name not in expected):
                report.warn("clips/", f"{extra} belongs to no moment")

    # Questions: their moments and quoted utterances exist.
    if questions is not None:
        asked: set[str] = set()
        for question in [*questions.operating, *questions.reviewer]:
            asked.add(question.moment_id)
            if moment_ids is not None and question.moment_id not in moment_ids:
                report.error(
                    "questions.json", f"{question.id}: moment {question.moment_id} doesn't exist"
                )
            if (
                question.quote is not None
                and utterance_ids is not None
                and question.quote.utterance_id not in utterance_ids
            ):
                report.error(
                    "questions.json",
                    f"{question.id}: utterance {question.quote.utterance_id} doesn't exist",
                )
        for moment_id in sorted((moment_ids or set()) - asked):
            report.warn("questions.json", f"no question about {moment_id}")

    # Seed records: their moments, utterances and media exist; every filled field is grounded.
    for record in records:
        name = "seed_records.json"
        label = f"record {record.id}"
        if (
            record.moment_id is not None
            and moment_ids is not None
            and record.moment_id not in moment_ids
        ):
            report.error(name, f"{label}: moment {record.moment_id} doesn't exist")
        for item in record.evidence:
            if isinstance(item, TranscriptEvidence) and utterance_ids is not None:
                if item.utterance_id not in utterance_ids:
                    report.error(name, f"{label}: utterance {item.utterance_id} doesn't exist")
            if (
                isinstance(item, MediaEvidence)
                and not (case_dir / item.uri.split("#")[0]).is_file()
            ):
                report.error(name, f"{label}: {item.uri} points to a missing file")
        missing = ungrounded_fields(record)
        if missing:
            report.error(name, f"{label}: filled fields without grounding (G5): {missing}")

    report.checked.append("cross-file references, times, clips and grounding")
    return report


# ── Procedure Reference ───────────────────────────────────────────────────────


def validate_reference(path: Path) -> Report:
    """Check a Procedure Reference file (`reference/<procedure_id>.json`)."""
    report = Report(f"reference {path}")
    if not path.is_file():
        raise ToolError(f"not a file: {path}")
    text = _read(path, report)
    reference = None if text is None else _parse(ProcedureReference, text, path.name, report)
    if reference is not None:
        report.checked.append(path.name)
        if path.stem != reference.id:
            report.error(
                path.name, f"the file of procedure {reference.id} must be {reference.id}.json"
            )
    return report


# ── Brain API ─────────────────────────────────────────────────────────────────


def load_endpoints() -> Mapping[str, Any]:
    """Dev2's `ENDPOINTS` registry (`scrubgpt_contracts.models.brain_api`)."""
    try:
        from scrubgpt_contracts.models import brain_api
    except ImportError as exc:
        raise ToolError(
            f"models/brain_api.py (Dev2) isn't available yet, so there is no ENDPOINTS: {exc}"
        ) from None
    endpoints = getattr(brain_api, "ENDPOINTS", None)
    if not isinstance(endpoints, Mapping) or not endpoints:
        raise ToolError("models/brain_api.py has no ENDPOINTS registry")
    return endpoints


def _check_body(
    report: Report, where: str, model: type[BaseModel], body: bytes | str
) -> BaseModel | None:
    try:
        data = json.loads(body)
    except ValueError:
        report.error(where, "the body is not JSON")
        return None
    if not isinstance(data, dict) or "contract_version" not in data:
        report.error(where, "the body has no contract_version (§4.1: every response carries it)")
    return _parse(model, body, where, report)


def validate_response(
    endpoint: str, path: Path, endpoints: Mapping[str, Any] | None = None
) -> Report:
    """Check a saved Brain API response body (or an `ApiError` body) for one endpoint."""
    endpoints = load_endpoints() if endpoints is None else endpoints
    if endpoint not in endpoints:
        raise ToolError(f"unknown endpoint {endpoint!r}; known: {sorted(endpoints)}")
    report = Report(f"response {endpoint} {path}")
    text = _read(path, report)
    if text is None:
        return report
    try:
        is_error = "error" in json.loads(text)
    except (ValueError, TypeError):
        is_error = False
    model = ApiError if is_error else endpoints[endpoint].response
    if _check_body(report, path.name, model, text) is not None:
        report.checked.append(f"{path.name} as {model.__name__}")
    return report


def _request_files(fixtures: Path, name: str, fields: Iterable[str]) -> dict[str, tuple] | None:
    files = {}
    for file_field in fields:
        matches = sorted(fixtures.glob(f"{name}.request.{file_field}.*"))
        if not matches:
            return None
        path = matches[0]
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        files[file_field] = (path.name, path.read_bytes(), content_type)
    return files


def run_live(
    client: httpx.Client,
    endpoints: Mapping[str, Any],
    fixtures: Path,
    *,
    target: str = "live",
) -> Report:
    """Call every endpoint with its request fixture and check each response (D-037).

    Each POST endpoint is also sent an empty request, which must fail with HTTP 400 and an
    `ApiError` body with code `bad_request` (§4.1: FastAPI's 422 is mapped to 400).
    """
    report = Report(target)
    for name in sorted(endpoints):
        endpoint = endpoints[name]
        method = str(endpoint.method).upper()
        path = endpoint.path
        where = f"{name} ({method} {path})"
        file_fields = tuple(getattr(endpoint, "files", ()) or ())
        request_model = getattr(endpoint, "request", None)
        kwargs: dict[str, Any] = {}
        if method == "POST":
            fixture = fixtures / f"{name}.request.json"
            if not fixture.is_file():
                report.error(where, f"request fixture missing: {fixture}")
                continue
            text = fixture.read_text(encoding="utf-8")
            if (
                request_model is not None
                and _parse(request_model, text, fixture.name, report) is None
            ):
                continue
            payload = json.loads(text)
            if file_fields:
                files = _request_files(fixtures, name, file_fields)
                if files is None:
                    report.error(where, f"file fixture missing: {name}.request.<field>.<ext>")
                    continue
                form = {k: v if isinstance(v, str) else json.dumps(v) for k, v in payload.items()}
                kwargs = {"data": form, "files": files}
            else:
                kwargs = {"json": payload}
        try:
            response = client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            report.error(where, f"request failed: {exc}")
            continue
        if response.status_code != 200:
            detail = ""
            error = (
                _parse(ApiError, response.content, where, Report("")) if response.content else None
            )
            if error is not None:
                detail = f": {error.error.code.value}: {error.error.message}"
            report.error(where, f"HTTP {response.status_code}{detail}")
            continue
        if _check_body(report, where, endpoint.response, response.content) is not None:
            report.checked.append(where)

        if method == "POST":
            probe = f"{name} (empty request)"
            try:
                bad = client.request(
                    method, path, **({"data": {}} if file_fields else {"json": {}})
                )
            except httpx.HTTPError as exc:
                report.error(probe, f"request failed: {exc}")
                continue
            if bad.status_code != 400:
                report.error(probe, f"expected HTTP 400 bad_request, got {bad.status_code}")
                continue
            error = _check_body(report, probe, ApiError, bad.content)
            if error is not None and error.error.code is not ErrorCode.BAD_REQUEST:
                report.error(probe, f"expected code bad_request, got {error.error.code.value}")
            elif error is not None:
                report.checked.append(probe)
    return report


# ── Command line ──────────────────────────────────────────────────────────────


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scrubgpt-validate",
        description=f"Check ScrubGPT files and a running Brain against contract {CONTRACT_VERSION}",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    case = commands.add_parser("case", help="a case package folder (plan §4.2)")
    case.add_argument("dir", type=Path)
    case.add_argument(
        "--reference",
        type=Path,
        help="Procedure Reference to use (default: <DATA_DIR>/reference/<procedure>.json)",
    )
    reference = commands.add_parser("reference", help="a Procedure Reference file (§4.2b)")
    reference.add_argument("file", type=Path)
    response = commands.add_parser("response", help="a saved Brain API response body (§4.4)")
    response.add_argument("endpoint")
    response.add_argument("file", type=Path)
    live = commands.add_parser("live", help="call every endpoint of a running Brain (D-037)")
    live.add_argument("--base-url", required=True)
    live.add_argument("--fixtures", type=Path, default=FIXTURES_DIR / "brain_api")
    live.add_argument("--timeout", type=float, default=120.0, help="seconds per request")
    return parser


def _run(args: argparse.Namespace) -> Report:
    if args.command == "case":
        return validate_case(args.dir, args.reference)
    if args.command == "reference":
        return validate_reference(args.file)
    if args.command == "response":
        return validate_response(args.endpoint, args.file)
    endpoints = load_endpoints()
    if not args.fixtures.is_dir():
        raise ToolError(f"request fixtures folder not found: {args.fixtures}")
    with httpx.Client(base_url=args.base_url, timeout=args.timeout) as client:
        return run_live(client, endpoints, args.fixtures, target=f"live {args.base_url}")


def main(argv: list[str] | None = None, *, out: Callable[[str], None] = print) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="backslashreplace")
    args = _parser().parse_args(argv)
    try:
        report = _run(args)
    except ToolError as exc:
        out(f"scrubgpt-validate: cannot run: {exc}")
        return 2
    out(report.render())
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
