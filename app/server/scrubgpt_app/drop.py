"""Drop mode (D-038): validate a Friday data drop file by file.

A drop (`<Drive>/drop/YYYY-MM-DD/`) holds case packages Dev1 copied over; partial packages are
expected (`video.mp4` comes only for the golden cases). Each package is checked with
`validate_case(..., drop=True)`, the same rule as `scrubgpt-validate case --drop` (issue #13), and
the result is reported **per file**, so the drop log can say exactly which files are wrong.
Nothing is loaded or changed.
"""

from dataclasses import dataclass, field
from pathlib import Path

from scrubgpt_contracts.models.case_package import JSON_FILES, REQUIRED_FILES
from scrubgpt_contracts.validate import Issue, ToolError, validate_case

CROSS_FILE = "cross-file"
"""Issues that involve several files (e.g. a moment's step missing from the timeline)."""

REQUIRED_FILES_PLAIN = {name.rstrip("/") for name in REQUIRED_FILES}


@dataclass
class FileResult:
    name: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "error" if self.errors else "warning" if self.warnings else "ok"


@dataclass
class PackageResult:
    folder: Path
    files: dict[str, FileResult] = field(default_factory=dict)
    not_run: list[str] = field(default_factory=list)

    @property
    def loadable(self) -> bool:
        """Complete and valid: the app would load it. A missing `video.mp4` is only a warning in
        drop mode, but the server needs the video to load the case."""
        return (
            not self.not_run
            and all(result.status != "error" for result in self.files.values())
            and (self.folder / "video.mp4").is_file()
        )


def _file_of(issue: Issue) -> str:
    """The package file an issue is about: `seed_records.json: records[2]` → `seed_records.json`."""
    head = issue.where.split(":", 1)[0].strip().rstrip("/")
    known = {name.rstrip("/") for name in (*REQUIRED_FILES, *JSON_FILES)}
    return head if head in known else CROSS_FILE


def check_package(folder: Path, reference: Path | None = None) -> PackageResult:
    result = PackageResult(folder)
    for name in dict.fromkeys(name.rstrip("/") for name in (*REQUIRED_FILES, *JSON_FILES)):
        result.files[name] = FileResult(name)
    try:
        report = validate_case(folder, reference, drop=True)
    except ToolError as exc:
        result.not_run.append(str(exc))
        return result
    for issue in report.issues:
        name = _file_of(issue)
        target = result.files.setdefault(name, FileResult(name))
        text = f"{issue.where}: {issue.message}" if name == CROSS_FILE else issue.message
        (target.errors if issue.level == "error" else target.warnings).append(text)
    result.not_run.extend(report.blocked)
    # Optional files that are absent and fine are left out of the report.
    for name in [n for n, r in result.files.items() if n not in REQUIRED_FILES_PLAIN]:
        if result.files[name].status == "ok" and not (folder / name).exists():
            del result.files[name]
    return result


def package_folders(drop_dir: Path) -> list[Path]:
    """The case folders of a drop: `<drop>/cases/<case_id>/` or `<drop>/<case_id>/`."""
    base = drop_dir / "cases" if (drop_dir / "cases").is_dir() else drop_dir
    return sorted(p for p in base.iterdir() if p.is_dir() and p.name != "reference")


def find_reference(drop_dir: Path, data_dir: Path) -> Path | None:
    """The Procedure Reference for a drop: the only `*.json` in `<drop>/reference/`, else in
    `<DATA_DIR>/reference/`; `None` lets the validator look it up itself."""
    for folder in (drop_dir / "reference", data_dir / "reference"):
        files = sorted(folder.glob("*.json")) if folder.is_dir() else []
        if len(files) == 1:
            return files[0]
    return None


def check_drop(drop_dir: Path, reference: Path | None) -> list[PackageResult]:
    if not drop_dir.is_dir():
        raise ToolError(f"not a folder: {drop_dir}")
    return [check_package(folder, reference) for folder in package_folders(drop_dir)]


def render(drop_dir: Path, results: list[PackageResult]) -> str:
    lines = [f"scrubgpt-app drop: {drop_dir}"]
    if not results:
        lines.append("  no case folders found")
    for package in results:
        verdict = "LOADABLE" if package.loadable else "NOT LOADABLE"
        lines.append(f"  {package.folder.name}: {verdict}")
        for reason in package.not_run:
            lines.append(f"    NOT RUN {reason}")
        for result in package.files.values():
            lines.append(f"    {result.status.upper():7} {result.name}")
            lines += [f"      error: {text}" for text in result.errors]
            lines += [f"      warning: {text}" for text in result.warnings]
    loadable = sum(package.loadable for package in results)
    lines.append(f"{loadable} of {len(results)} package(s) loadable")
    return "\n".join(lines)
