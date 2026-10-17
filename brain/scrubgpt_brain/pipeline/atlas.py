"""A6 Visual step atlas (plan §2.1): 2–3 reference frames per rule-book step, taken from GraSP's
ground-truth labels. C2 shows them to GPT as examples of what each step looks like (few-shot, no
training), cached with prompt caching (brain/CLAUDE.md rule 5).

Two stages, so the choice can be made and checked before any video is at hand:
1. **Pick** (`pick_atlas`, `scrubgpt-brain atlas pick`): which moments, from the labels alone. It
   writes the index `knowledge/atlas/<procedure>.yaml` (in git): for each step, the GraSP case and
   second of each frame, and why it was chosen. No images.
2. **Extract** (`extract_atlas`, `scrubgpt-brain atlas frames`): the images, cut from each GraSP
   case's video with FFmpeg into `<DATA_DIR>/atlas/<procedure>/<step_id>/<CASE>_<ms>.jpg`, plus
   the manifest `atlas.json` that C2 reads (`load_atlas`). Images never go into git.

**Which frames:**
- **Only GraSP's train cases.** The 5 test cases (`GRASP_TEST_CASES`) are kept for the accuracy
  score (C7), so the score stays honest (brain/CLAUDE.md rule 8). The pick refuses them.
- **Exact keyframes first.** Keyframes map to rule-book steps as in B1 (`grasp.map_keyframes`). A
  keyframe is *exact* when its GraSP label names that one step. A label naming several steps
  (*ambiguous*, resolved by continuity) is right for a timeline but weaker for an example picture.
  **Generic acts** (suction, cutting) are never used: they look the same in every step.
- **Well inside a step.** A *run* is consecutive keyframes of one step; idle, or another step, ends
  it. A frame is the middle keyframe of a run at least `min_run_s` long, so it sits away from the
  transitions.
- **Variety.** Up to `per_step` frames per step, from different cases first (other patients, other
  camera set-ups), longest run first. With fewer cases than `per_step`, a case gives another frame
  from a different run, at least `min_gap_s` away. Exact runs come first; runs of ambiguous
  keyframes only fill up a step that has too few (`basis: ambiguous`).
- **Gaps are listed.** A step that no GraSP label reaches goes under `missing`. Its examples must
  come from elsewhere (PSI-AVA or a YouTube case, plan §7).

The same labels always give the same index.

**Time** is in seconds of the GraSP video, which equals `frame_num` in GraSP's 1 fps annotation
files, the recommended input. B3 doesn't cut, so this is also the same second of the normalised
`video.mp4`. Atlas images are scaled to 720 px high, like B3's video, so the examples look like
the frames C2 is asked about.
"""

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

from scrubgpt_brain.engines.media import MediaError, check_image, probe, run, tool
from scrubgpt_brain.engines.rulebook import KNOWLEDGE_DIR, RuleBook, load_knowledge
from scrubgpt_brain.pipeline.grasp import MappedKeyframe, map_keyframes, read_all_labels

GRASP_TEST_CASES = frozenset({"CASE041", "CASE047", "CASE050", "CASE051", "CASE053"})
"""GraSP's official test split (`grasp_long-term_test.json`): never atlas material."""

PER_STEP = 3
MIN_RUN_S = 10.0
MIN_GAP_S = 60.0
FRAME_HEIGHT = 720
MANIFEST_NAME = "atlas.json"
DRAFT = "draft_pending_urologist_review"
VIDEO_SUFFIXES = (".mp4", ".mkv", ".mov", ".avi", ".m4v", ".webm")

Basis = Literal["exact", "ambiguous"]


class AtlasError(ValueError):
    """The labels, the index or the videos don't allow a valid atlas."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("; ".join(problems))


@dataclass(frozen=True)
class AtlasFrame:
    """One reference frame of a step."""

    grasp_case: str
    t: float
    """Seconds from the start of the GraSP video."""
    run: tuple[float, float]
    """The run of keyframes it is the middle of (start, end), in seconds."""
    grasp_step: str
    """The GraSP step code at `t`."""
    basis: Basis


@dataclass(frozen=True)
class AtlasIndex:
    """`knowledge/atlas/<procedure>.yaml`: the chosen frames per step."""

    procedure_id: str
    source: str
    cases: tuple[str, ...]
    per_step: int
    min_run_s: float
    min_gap_s: float
    review_status: str
    """`draft_pending_urologist_review` until a surgeon has looked at every image (as in every
    knowledge file)."""
    steps: dict[str, tuple[AtlasFrame, ...]]
    missing: tuple[str, ...]


def index_path(procedure_id: str, knowledge_dir: Path = KNOWLEDGE_DIR) -> Path:
    """Where the index of a procedure lives: `knowledge/atlas/<procedure_id>.yaml`."""
    return knowledge_dir / "atlas" / f"{procedure_id}.yaml"


def atlas_name(grasp_case: str, t: float) -> str:
    """`atlas_name("CASE001", 812.0)` → `"CASE001_000812000.jpg"` (milliseconds)."""
    return f"{grasp_case}_{round(t * 1000):09d}.jpg"


@dataclass(frozen=True)
class _Run:
    step_id: str
    case: str
    frames: tuple[MappedKeyframe, ...]

    @property
    def length(self) -> float:
        return self.frames[-1].end - self.frames[0].t

    @property
    def middle(self) -> MappedKeyframe:
        return self.frames[(len(self.frames) - 1) // 2]


def _runs(case: str, keyframes: list[MappedKeyframe], *, exact_only: bool) -> list[_Run]:
    """Maximal runs of consecutive keyframes with one step (exact keyframes only, if asked)."""
    runs: list[_Run] = []
    current: list[MappedKeyframe] = []
    for frame in [*keyframes, None]:
        usable = frame is not None and (
            frame.mapping == "exact" or (frame.mapping == "ambiguous" and not exact_only)
        )
        if current and (not usable or frame is None or frame.step_id != current[0].step_id):
            runs.append(_Run(current[0].step_id or "", case, tuple(current)))
            current = []
        if usable and frame is not None:
            current.append(frame)
    return runs


def _choose(
    runs: list[_Run], taken: list[tuple[_Run, Basis]], per_step: int, min_gap_s: float, basis: Basis
) -> None:
    """Add runs to `taken` up to `per_step`: a new case first, longest run first; then more runs
    of cases already used, at least `min_gap_s` from that case's chosen frames."""
    ranked = sorted(runs, key=lambda r: (-r.length, r.case, r.frames[0].t))
    for new_cases_only in (True, False):
        for run_ in ranked:
            if len(taken) >= per_step:
                return
            used = [r for r, _ in taken if r.case == run_.case]
            if new_cases_only and used:
                continue
            if any(abs(r.middle.t - run_.middle.t) < min_gap_s for r in used):
                continue
            if any(r is run_ or r.frames == run_.frames for r, _ in taken):
                continue
            taken.append((run_, basis))


def pick_atlas(
    annotations: Path,
    *,
    cases: list[str] | None = None,
    per_step: int = PER_STEP,
    min_run_s: float = MIN_RUN_S,
    min_gap_s: float = MIN_GAP_S,
    video_fps: float | None = None,
    knowledge_dir: Path = KNOWLEDGE_DIR,
) -> AtlasIndex:
    """Choose the atlas frames from a GraSP long-term annotation file (all its cases, or `cases`).

    Raises `AtlasError` for a GraSP test case or a case the file lacks, and `GraspError` (from
    B1) if the file can't be read or doesn't match the crosswalk."""
    if per_step < 1 or min_run_s <= 0 or min_gap_s < 0:
        raise AtlasError(
            [
                f"per_step >= 1, min_run_s > 0, min_gap_s >= 0 (got {per_step}, {min_run_s}, "
                f"{min_gap_s})"
            ]
        )
    rulebook = load_knowledge(knowledge_dir).rulebook
    labels = read_all_labels(annotations, video_fps=video_fps, crosswalk=rulebook.grasp)
    chosen = sorted(labels) if cases is None else list(dict.fromkeys(cases))
    problems = [f"{c}: a GraSP test case (kept for C7)" for c in chosen if c in GRASP_TEST_CASES]
    problems += [f"{c}: not in {annotations.name}" for c in chosen if c not in labels]
    if not chosen:
        problems.append(f"{annotations.name}: no cases")
    if problems:
        raise AtlasError(problems)
    keyframes = {case: map_keyframes(labels[case], rulebook) for case in chosen}
    steps: dict[str, tuple[AtlasFrame, ...]] = {}
    missing: list[str] = []
    for step in rulebook.steps():
        taken: list[tuple[_Run, Basis]] = []
        for basis in ("exact", "ambiguous"):
            runs = [
                r
                for case in chosen
                for r in _runs(case, keyframes[case], exact_only=basis == "exact")
                if r.step_id == step.id and r.length >= min_run_s - 1e-9
            ]
            _choose(runs, taken, per_step, min_gap_s, basis)
        if not taken:
            missing.append(step.id)
            continue
        steps[step.id] = tuple(
            AtlasFrame(
                grasp_case=r.case,
                t=round(r.middle.t, 3),
                run=(round(r.frames[0].t, 3), round(r.frames[-1].end, 3)),
                grasp_step=r.middle.code,
                basis=basis,
            )
            for r, basis in sorted(taken, key=lambda item: (item[0].case, item[0].middle.t))
        )
    return AtlasIndex(
        procedure_id=rulebook.id,
        source=annotations.name,
        cases=tuple(chosen),
        per_step=per_step,
        min_run_s=min_run_s,
        min_gap_s=min_gap_s,
        review_status=DRAFT,
        steps=steps,
        missing=tuple(missing),
    )


_HEADER = """\
# A6 step atlas index: the reference frames of each step (GraSP case + second of the video).
# Written by `scrubgpt-brain atlas pick`; regenerate it rather than editing by hand.
# The images are cut by `scrubgpt-brain atlas frames` into <DATA_DIR>/atlas/<procedure_id>/,
# never into git. `review_status` stays a draft until a surgeon has looked at every image.
"""


def index_yaml(index: AtlasIndex) -> str:
    """The index as YAML (what `write_index` saves)."""
    data = {
        "procedure_id": index.procedure_id,
        "source": index.source,
        "cases": list(index.cases),
        "per_step": index.per_step,
        "min_run_s": index.min_run_s,
        "min_gap_s": index.min_gap_s,
        "review_status": index.review_status,
        "steps": {
            step_id: [
                {
                    "grasp_case": f.grasp_case,
                    "t": f.t,
                    "run": list(f.run),
                    "grasp_step": f.grasp_step,
                    "basis": f.basis,
                }
                for f in frames
            ]
            for step_id, frames in index.steps.items()
        },
        "missing": list(index.missing),
    }
    body = yaml.safe_dump(
        data, sort_keys=False, allow_unicode=True, width=100, default_flow_style=None
    )
    return _HEADER + body


def write_index(index: AtlasIndex, path: Path) -> Path:
    """Save the index atomically (LF line endings)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    part.write_text(index_yaml(index), encoding="utf-8", newline="\n")
    os.replace(part, path)
    return path


def load_index(path: Path, *, knowledge_dir: Path = KNOWLEDGE_DIR) -> AtlasIndex:
    """Read and check an index against the rule book. Raises `AtlasError` listing every
    problem."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise AtlasError([f"can't read {path}: {exc}"]) from None
    if not isinstance(data, dict):
        raise AtlasError([f"{path.name}: not a mapping"])
    rulebook: RuleBook = load_knowledge(knowledge_dir).rulebook
    known = {step.id for step in rulebook.steps()}
    problems: list[str] = []
    if data.get("procedure_id") != rulebook.id:
        problems.append(
            f"{path.name}: procedure_id {data.get('procedure_id')!r} isn't the rule book's "
            f"{rulebook.id!r}"
        )
    steps: dict[str, tuple[AtlasFrame, ...]] = {}
    for step_id, frames in (data.get("steps") or {}).items():
        if step_id not in known:
            problems.append(f"{path.name}: {step_id}: not a rule-book step")
            continue
        parsed = []
        for i, item in enumerate(frames or []):
            where = f"{path.name}: {step_id}[{i}]"
            try:
                frame = AtlasFrame(
                    grasp_case=str(item["grasp_case"]),
                    t=float(item["t"]),
                    run=(float(item["run"][0]), float(item["run"][1])),
                    grasp_step=str(item["grasp_step"]),
                    basis=item["basis"],
                )
            except (KeyError, TypeError, ValueError, IndexError) as exc:
                problems.append(f"{where}: malformed ({exc!r})")
                continue
            if frame.grasp_case in GRASP_TEST_CASES:
                problems.append(f"{where}: {frame.grasp_case} is a GraSP test case")
            if not (math.isfinite(frame.t) and frame.run[0] <= frame.t < frame.run[1]):
                problems.append(f"{where}: t {frame.t} must lie in its run {list(frame.run)}")
            if frame.t < 0:
                problems.append(f"{where}: t must be >= 0")
            if frame.basis not in ("exact", "ambiguous"):
                problems.append(f"{where}: basis must be exact or ambiguous")
            parsed.append(frame)
        steps[step_id] = tuple(parsed)
    missing = tuple(data.get("missing") or ())
    for step_id in missing:
        if step_id not in known:
            problems.append(f"{path.name}: missing: {step_id}: not a rule-book step")
        elif steps.get(step_id):
            problems.append(f"{path.name}: {step_id} has frames and is listed as missing")
    if problems:
        raise AtlasError(problems)
    return AtlasIndex(
        procedure_id=data["procedure_id"],
        source=str(data.get("source", "")),
        cases=tuple(data.get("cases") or ()),
        per_step=int(data.get("per_step", PER_STEP)),
        min_run_s=float(data.get("min_run_s", MIN_RUN_S)),
        min_gap_s=float(data.get("min_gap_s", MIN_GAP_S)),
        review_status=str(data.get("review_status", DRAFT)),
        steps=steps,
        missing=missing,
    )


def find_video(videos: Path, grasp_case: str) -> Path | None:
    """A GraSP case's video in `videos`: `<CASE>.mp4` (or another video suffix), else a B3 output
    folder `<CASE>/video.mp4`."""
    for suffix in VIDEO_SUFFIXES:
        if (videos / f"{grasp_case}{suffix}").is_file():
            return videos / f"{grasp_case}{suffix}"
    normalised = videos / grasp_case / "video.mp4"
    return normalised if normalised.is_file() else None


def _cut(video: Path, t: float, target: Path, height: int) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.stem + ".part.jpg")
    args = [tool("ffmpeg"), "-hide_banner", "-nostdin", "-y", "-v", "error"]
    args += ["-ss", f"{t:.6f}", "-i", str(video), "-frames:v", "1"]
    args += ["-vf", f"scale=-2:{height},setsar=1", "-q:v", "2"]
    args += ["-c:v", "mjpeg", "-update", "1", "-f", "image2", str(part)]
    try:
        run(args, timeout=600)
        if not part.is_file():
            raise MediaError(f"ffmpeg wrote no frame at {t} s of {video}")
        check_image(part)
    except MediaError:
        part.unlink(missing_ok=True)
        raise
    os.replace(part, target)


def _is_image(path: Path) -> bool:
    try:
        check_image(path)
    except MediaError:
        return False
    return True


def extract_atlas(
    videos: Path,
    data_dir: Path,
    *,
    index: Path | None = None,
    height: int = FRAME_HEIGHT,
    knowledge_dir: Path = KNOWLEDGE_DIR,
) -> Path:
    """Cut every frame of the index (default: the rule book's `knowledge/atlas/<id>.yaml`) from
    the GraSP videos in `videos`, into `<data_dir>/atlas/<procedure_id>/`, and write the manifest.
    Frames already there are kept, so a re-run only cuts what is missing. Returns the manifest.

    Raises `AtlasError` (an invalid index, a missing video, a time past a video's end) before
    cutting anything, and `MediaError` if FFmpeg fails."""
    if index is None:
        index = index_path(load_knowledge(knowledge_dir).rulebook.id, knowledge_dir)
    atlas = load_index(index, knowledge_dir=knowledge_dir)
    needed: dict[str, float] = {}
    for frames in atlas.steps.values():
        for frame in frames:
            needed[frame.grasp_case] = max(needed.get(frame.grasp_case, 0.0), frame.t)
    found = {case: find_video(videos, case) for case in sorted(needed)}
    problems = [
        f"{case}: no video in {videos} (looked for {case}.mp4 and {case}/video.mp4)"
        for case, video in found.items()
        if video is None
    ]
    for case, video in found.items():
        if video is not None:
            duration = probe(video).duration_s
            if needed[case] >= duration:
                problems.append(
                    f"{case}: a frame at {needed[case]} s, but {video.name} is {duration:.1f} s "
                    "long (the wrong video?)"
                )
    if problems:
        raise AtlasError(problems)
    out = data_dir / "atlas" / atlas.procedure_id
    manifest: dict[str, list[dict]] = {}
    for step_id, frames in atlas.steps.items():
        entries = []
        for frame in frames:
            relative = f"{step_id}/{atlas_name(frame.grasp_case, frame.t)}"
            target = out / relative
            if not (target.is_file() and _is_image(target)):
                video = found[frame.grasp_case]
                assert video is not None
                _cut(video, frame.t, target, height)
            entries.append(
                {
                    "file": relative,
                    "grasp_case": frame.grasp_case,
                    "t": frame.t,
                    "grasp_step": frame.grasp_step,
                    "basis": frame.basis,
                }
            )
        manifest[step_id] = entries
    path = out / MANIFEST_NAME
    part = out / (MANIFEST_NAME + ".part")
    body = {
        "procedure_id": atlas.procedure_id,
        "index": index.name,
        "height": height,
        "review_status": atlas.review_status,
        "steps": manifest,
        "missing": list(atlas.missing),
    }
    part.write_text(
        json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    os.replace(part, path)
    return path


def load_atlas(data_dir: Path, procedure_id: str = "rarp") -> dict[str, list[Path]]:
    """The atlas images per step id, from the manifest `extract_atlas` wrote (for C2).

    Raises `FileNotFoundError` if the manifest or one of its images is missing, `ValueError` if
    the manifest is malformed."""
    folder = data_dir / "atlas" / procedure_id
    text = (folder / MANIFEST_NAME).read_text(encoding="utf-8")
    try:
        steps = json.loads(text)["steps"]
        images = {s: [folder / e["file"] for e in entries] for s, entries in steps.items()}
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"not an atlas manifest: {folder / MANIFEST_NAME} ({exc})") from None
    for paths in images.values():
        for path in paths:
            if not path.is_file():
                raise FileNotFoundError(f"atlas image missing: {path}")
    return images
