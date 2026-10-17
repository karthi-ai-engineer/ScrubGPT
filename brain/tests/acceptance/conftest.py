"""Shared fixtures for Tester 1's acceptance tests of A1-A4 (`knowledge/`) and B3/C1 (`brain/`).

Test files can't import each other under `--import-mode=importlib`, so the helpers live here and
reach the tests as fixtures. Everything is read from the working tree; nothing imports the
contracts package (D-051, D-063) and nothing is written outside `tmp_path`. All media is synthetic,
made by FFmpeg's `testsrc2`, `smptebars` and `sine` sources in `tmp_path` (D-036); the `media`
fixture skips its tests when the FFmpeg CLI is missing (#12 AC8).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from collections.abc import Callable, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml
from PIL import Image, ImageChops, ImageStat

REPO_ROOT = Path(__file__).resolve().parents[3]
KNOWLEDGE = REPO_ROOT / "knowledge"
RULEBOOK_PATH = KNOWLEDGE / "rulebooks" / "rarp.yaml"
ONTOLOGY_PATH = KNOWLEDGE / "ontology" / "core.yaml"
TAXONOMY_PATH = KNOWLEDGE / "taxonomy" / "obstacles.yaml"
VOCAB_PATH = KNOWLEDGE / "vocab" / "terms.yaml"
REFERENCE_FIXTURE_PATH = REPO_ROOT / "contracts" / "fixtures" / "reference" / "rarp.json"

REVIEW_STATUS = "draft_pending_urologist_review"  # knowledge/README.md

# ID patterns copied from the contract (plan §4.1, §4.2b; D-035), not imported (D-051).
SLUG = r"[a-z0-9]+(?:_[a-z0-9]+)*"
FAMILIES = (
    "bleeding",
    "anatomical_variation",
    "tissue_condition",
    "visibility",
    "technical_difficulty",
    "equipment",
    "patient_condition",
    "unexpected_finding",
)
PHASE_ID_RE = re.compile(r"^rarp\.p[0-9]{2,}$")
STEP_ID_RE = re.compile(r"^rarp\.p[0-9]{2,}\.s[0-9]{2,}$")
CHECKPOINT_ID_RE = re.compile(r"^rarp\.p[0-9]{2,}\.s[0-9]{2,}\.c[1-9][0-9]*$")
LEAF_ID_RE = re.compile(rf"^(?:{'|'.join(FAMILIES)})\.{SLUG}$")
SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")


class _UniqueKeyLoader(yaml.SafeLoader):
    """A SafeLoader that refuses duplicate mapping keys (safe_load keeps the last one silently)."""


def _construct_unique_mapping(loader: _UniqueKeyLoader, node: yaml.MappingNode) -> dict:
    seen: set[Any] = set()
    for key_node, _value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if key in seen:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"duplicate key {key!r}",
                key_node.start_mark,
            )
        seen.add(key)
    return loader.construct_mapping(node, deep=True)


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


def _safe_load(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def walk(node: Any, path: str = "$") -> Iterator[tuple[str, Any]]:
    """Every (path, value) in a parsed YAML/JSON tree, containers included."""
    yield path, node
    if isinstance(node, dict):
        for key, value in node.items():
            yield from walk(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from walk(value, f"{path}[{index}]")


def strings(node: Any) -> Iterator[tuple[str, str]]:
    """Every string in a tree, mapping keys included, with its path."""
    for path, value in walk(node):
        if isinstance(value, str):
            yield path, value
        elif isinstance(value, dict):
            for key in value:
                if isinstance(key, str):
                    yield f"{path}.<key>", key


def bilingual_problems(node: Any) -> list[str]:
    """Paths of `{ja, en}` pairs where a half is missing, empty or blank (plan §4.1 Bilingual)."""
    problems: list[str] = []
    for path, value in walk(node):
        if not isinstance(value, dict) or not ({"ja", "en"} & set(value)):
            continue
        if not {"ja", "en"} <= set(value):
            problems.append(f"{path}: has only {sorted({'ja', 'en'} & set(value))}")
            continue
        ja, en = value["ja"], value["en"]
        if isinstance(ja, list) and isinstance(en, list):  # synonym lists: each entry non-empty
            for lang, items in (("ja", ja), ("en", en)):
                for index, item in enumerate(items):
                    if not isinstance(item, str) or not item.strip():
                        problems.append(f"{path}.{lang}[{index}]: {item!r}")
            continue
        for lang, text in (("ja", ja), ("en", en)):
            if not isinstance(text, str) or not text.strip():
                problems.append(f"{path}.{lang}: {text!r}")
    return problems


def is_bilingual(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("ja"), str)
        and isinstance(value.get("en"), str)
        and bool(value["ja"].strip())
        and bool(value["en"].strip())
    )


def normalise(text: str) -> str:
    """Surface form used to look a term up: NFKC, case-folded, whitespace collapsed."""
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def leaf_text(leaf_id: str, leaf: dict) -> str:
    """A leaf's slug and EN name as space-separated lower-case words, padded with spaces."""
    slug = leaf_id.split(".", 1)[-1]
    name = (leaf.get("name") or {}).get("en", "") if isinstance(leaf.get("name"), dict) else ""
    return " " + " ".join(re.sub(r"[^0-9a-z]+", " ", f"{slug} {name}".casefold()).split()) + " "


def has_word(text: str, keyword: str) -> bool:
    """`keyword` starts a word of `text` (a leaf_text); a trailing space also makes it end one.
    So "vascular" does not match "neurovascular", and "sv " matches only the word "sv"."""
    return " " + keyword.lstrip() in text


# ── Appendix A "Known obstacles" (plan Appendix A) ───────────────────────────


def _either(*clauses):
    """A leaf predicate that holds when any clause (a list of keyword groups) holds: every group
    of the clause has a keyword starting a word of the leaf's slug + EN name."""

    def predicate(family: str, text: str) -> bool:
        return any(
            all(any(has_word(text, k) for k in group) for group in clause) for clause in clauses
        )

    return predicate


def _in_family(required: str, *clauses):
    inner = _either(*clauses)
    return lambda family, text: family == required and inner(family, text)


# (Appendix A row #, obstacle as written there, predicate on (family id, leaf_text)).
# Bleeding obstacles sit under Bleeding; the median lobe under Anatomical variation (plan §4.2b
# example `anatomical_variation.median_lobe`). Row 8's "Adherent plane / rectal injury risk" is one
# item, so a leaf for either half covers it.
APPENDIX_A_OBSTACLES = [
    (1, "Adhesions from prior surgery",
     _either([["adhesion"], ["prior", "previous", "surgery", "surgical"]])),
    (1, "Obesity", _either([["obes"]])),
    (2, "Vessel bleeding", _in_family("bleeding", [["vessel", "iliac", "vascular", "obturator"]])),
    (2, "Nerve proximity", _either([["nerve"], ["proxim", "close", "near"]])),
    (3, "Hernia-mesh adhesions", _either([["mesh"]])),
    (3, "Obesity", _either([["obes"]])),
    (4, "DVC (Santorini) bleeding", _in_family("bleeding", [["dvc", "santorini", "dorsal vein"]])),
    (5, "Median lobe", _in_family("anatomical_variation", [["median lobe", "middle lobe"]])),
    (5, "Large prostate", _either([["large prostate", "enlarged prostate", "prostatomegaly"]])),
    (5, "Prior TURP", _either([["turp", "transurethral resection"]])),
    (6, "Median lobe", _in_family("anatomical_variation", [["median lobe", "middle lobe"]])),
    (6, "Wide bladder neck", _either([["wide"], ["bladder neck"]])),
    (7, "Inflammation", _either([["inflam"]])),
    (7, "Bleeding from SV artery", _in_family("bleeding", [["sv ", "seminal"], ["arter"]])),
    (8, "Adherent plane / rectal injury risk",
     _either([["rectal", "rectum"]], [["adher"], ["plane"]])),
    (9, "Pedicle/NVB bleeding", _in_family("bleeding", [["pedicle", "nvb", "neurovascular"]])),
    (9, "Accessory pudendal artery", _either([["pudendal"]])),
    (10, "Difficult apex", _either([["apex", "apical"]])),
    (10, "Positive-margin risk", _either([["margin"]])),
    (11, "Tissue tension", _either([["tension"]])),
    (12, "Anastomotic tension", _either([["anastomo"], ["tension"]])),
    (12, "Leak", _either([["leak"]])),
    (13, "Port-site bleeding", _in_family("bleeding", [["port"]])),
]  # fmt: skip


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Parametrize any test that asks for `appendix_a_obstacle` with the table above."""
    if "appendix_a_obstacle" in metafunc.fixturenames:
        metafunc.parametrize(
            "appendix_a_obstacle",
            APPENDIX_A_OBSTACLES,
            ids=[f"p{n:02d}-{label}" for n, label, _ in APPENDIX_A_OBSTACLES],
        )


# ── Loaded files ─────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def load_yaml() -> Callable[[Path], Any]:
    return _safe_load


@pytest.fixture(scope="session")
def load_yaml_unique_keys() -> Callable[[Path], Any]:
    def load(path: Path) -> Any:
        with path.open(encoding="utf-8") as handle:
            return yaml.load(handle, Loader=_UniqueKeyLoader)  # noqa: S506 (SafeLoader subclass)

    return load


@pytest.fixture(scope="session")
def rulebook() -> dict:
    return _safe_load(RULEBOOK_PATH)


@pytest.fixture(scope="session")
def ontology() -> dict:
    return _safe_load(ONTOLOGY_PATH)


@pytest.fixture(scope="session")
def taxonomy() -> dict:
    return _safe_load(TAXONOMY_PATH)


@pytest.fixture(scope="session")
def vocab() -> dict:
    return _safe_load(VOCAB_PATH)


# ── Derived views ────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def phases(rulebook: dict) -> list[dict]:
    return list(rulebook["phases"])


@pytest.fixture(scope="session")
def steps(phases: list[dict]) -> list[tuple[dict, dict]]:
    """Every (phase, step) pair, in order."""
    return [(phase, step) for phase in phases for step in phase.get("steps") or []]


@pytest.fixture(scope="session")
def defined_procedure_ids(phases: list[dict]) -> set[str]:
    """Phase, step and checkpoint ids defined in the rule book."""
    ids: set[str] = set()
    for phase in phases:
        ids.add(phase["id"])
        for step in phase.get("steps") or []:
            ids.add(step["id"])
            for checkpoint in step.get("checkpoints") or []:
                ids.add(checkpoint["id"])
    return ids


@pytest.fixture(scope="session")
def leaves(taxonomy: dict) -> dict[str, tuple[str, dict]]:
    """Leaf id -> (family id, leaf)."""
    found: dict[str, tuple[str, dict]] = {}
    for family in taxonomy["families"]:
        for leaf in family.get("leaves") or []:
            found[leaf["id"]] = (family["id"], leaf)
    return found


@pytest.fixture(scope="session")
def terms_by_id(vocab: dict) -> dict[str, dict]:
    return {term["id"]: term for term in vocab["terms"]}


@pytest.fixture(scope="session")
def surface_index(vocab: dict) -> dict[str, set[str]]:
    """Normalised surface form (ja, en and every synonym) -> the term ids it names."""
    index: dict[str, set[str]] = {}
    for term in vocab["terms"]:
        forms = [term.get("ja"), term.get("en")]
        synonyms = term.get("synonyms") or {}
        for lang in ("ja", "en"):
            forms.extend(synonyms.get(lang) or [])
        for form in forms:
            if isinstance(form, str) and form.strip():
                index.setdefault(normalise(form), set()).add(term["id"])
    return index


@pytest.fixture(scope="session")
def const() -> SimpleNamespace:
    """Paths, ID patterns and fixed values, for tests that can't import this module."""
    return SimpleNamespace(
        repo_root=REPO_ROOT,
        knowledge=KNOWLEDGE,
        rulebook_path=RULEBOOK_PATH,
        ontology_path=ONTOLOGY_PATH,
        taxonomy_path=TAXONOMY_PATH,
        vocab_path=VOCAB_PATH,
        reference_fixture_path=REFERENCE_FIXTURE_PATH,
        review_status=REVIEW_STATUS,
        families=FAMILIES,
        phase_id_re=PHASE_ID_RE,
        step_id_re=STEP_ID_RE,
        checkpoint_id_re=CHECKPOINT_ID_RE,
        leaf_id_re=LEAF_ID_RE,
        snake_case_re=SNAKE_CASE_RE,
    )


@pytest.fixture(scope="session")
def helpers() -> dict[str, Callable]:
    return {
        "walk": walk,
        "strings": strings,
        "bilingual_problems": bilingual_problems,
        "is_bilingual": is_bilingual,
        "normalise": normalise,
        "leaf_text": leaf_text,
    }


# ── B3/C1: synthetic media and the FFmpeg CLI (#12; D-036, D-063) ────────────

FFMPEG_TIMEOUT_S = 600
CLI_TIMEOUT_S = 900
FFMPEG_MISSING = (
    "the FFmpeg CLI (ffmpeg and ffprobe) is not on PATH: the FFmpeg-based tests (B3, C1, C5 on C1 "
    "frames, D1, B4's duration, B2's download, the media CLI commands) need it, so they skip "
    "(#12 AC8, #14 AC14; the CI runner has no FFmpeg)"
)
# The case JSON files of plan §4.2, which brain/ must not read or write before the tag (D-063).
CASE_JSON_NAMES = (
    "case.json",
    "timeline.json",
    "moments.json",
    "questions.json",
    "seed_records.json",
    "metrics.json",
    "trainee.json",
)


def _ffmpeg(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", *args],
        capture_output=True,
        check=True,
        timeout=FFMPEG_TIMEOUT_S,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _num(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def make_video(
    path: Path,
    duration: float,
    *,
    size: str = "426x240",
    rate: int = 25,
    audio: bool = True,
    first: str = "testsrc2",
    cut_at: float | None = None,
    second: str = "smptebars",
    vcodec: str = "libx264",
    acodec: str = "aac",
) -> Path:
    """A synthetic video: `first` for `duration` s, or `first` then a hard cut to `second` at
    `cut_at` s. With `audio`, a 440 Hz `sine` tone as a STEREO track (44.1 kHz AAC, or 48 kHz PCM
    for `acodec="pcm_s16le"`), so B3 must really resample and down-mix it."""
    if cut_at is None:
        inputs = ["-f", "lavfi", "-i", f"{first}=size={size}:rate={rate}:duration={_num(duration)}"]
        video_map = ["-map", "0:v:0"]
        audio_index = 1
    else:
        inputs = [
            "-f", "lavfi", "-i", f"{first}=size={size}:rate={rate}:duration={_num(cut_at)}",
            "-f", "lavfi", "-i",
            f"{second}=size={size}:rate={rate}:duration={_num(duration - cut_at)}",
        ]  # fmt: skip
        video_map = ["-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]", "-map", "[v]"]
        audio_index = 2
    audio_args: list[str] = []
    if audio:
        tone = f"sine=frequency=440:sample_rate=48000:duration={_num(duration)}"
        inputs += ["-f", "lavfi", "-i", tone]
        audio_args = ["-map", f"{audio_index}:a:0", "-ac", "2"]
        if acodec == "pcm_s16le":
            audio_args += ["-c:a", "pcm_s16le", "-ar", "48000"]
        else:
            audio_args += ["-c:a", acodec, "-ar", "44100"]
    if vcodec == "libx264":
        video_args = ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
    else:
        video_args = ["-c:v", vcodec, "-q:v", "5", "-pix_fmt", "yuv420p"]
    path.parent.mkdir(parents=True, exist_ok=True)
    _ffmpeg(
        "-y", "-v", "error", *inputs, *video_map, *video_args, *audio_args,
        "-t", _num(duration), str(path),
    )  # fmt: skip
    return path


def make_audio(path: Path, duration: float) -> Path:
    """An audio-only file (a `sine` tone, AAC): a non-video input for B3."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _ffmpeg(
        "-y", "-v", "error", "-f", "lavfi", "-i",
        f"sine=frequency=440:sample_rate=48000:duration={_num(duration)}",
        "-c:a", "aac", str(path),
    )  # fmt: skip
    return path


def ffprobe(path: Path) -> dict:
    """ffprobe's streams and format of `path`, as JSON."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True,
        check=True,
        timeout=FFMPEG_TIMEOUT_S,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout
    return json.loads(out)


def streams(probe: dict, kind: str) -> list[dict]:
    return [s for s in probe.get("streams", []) if s.get("codec_type") == kind]


def top_level_boxes(path: Path) -> list[str]:
    """The top-level ISO-BMFF box types of an MP4, in file order (`moov` before `mdat` is
    "faststart")."""
    kinds: list[str] = []
    total = path.stat().st_size
    with path.open("rb") as handle:
        offset = 0
        while offset + 8 <= total:
            handle.seek(offset)
            header = handle.read(8)
            size = int.from_bytes(header[:4], "big")
            kinds.append(header[4:8].decode("latin-1"))
            if size == 1:
                size = int.from_bytes(handle.read(8), "big")
            elif size == 0:
                size = total - offset
            if size < 8:
                raise ValueError(f"{path}: bad box size {size} at offset {offset}")
            offset += size
    return kinds


def max_volume_db(path: Path) -> float:
    """The peak level of the first audio stream (FFmpeg `volumedetect`), in dB."""
    result = _ffmpeg(
        "-v", "info", "-i", str(path), "-map", "0:a:0", "-af", "volumedetect", "-f", "null", "-",
    )  # fmt: skip
    found = re.findall(r"max_volume:\s*(-?[0-9.]+|-inf) dB", result.stderr)
    assert found, f"volumedetect printed no max_volume for {path}:\n{result.stderr[-2000:]}"
    return float(found[-1])


def decode_image(path: Path) -> tuple[str, tuple[int, int]]:
    """Fully decode an image with Pillow; returns (format, size). Raises if it isn't one."""
    with Image.open(path) as image:
        image.load()
        return image.format, image.size


def reference_frames(video: Path, indices: list[int], folder: Path) -> dict[int, Path]:
    """Decode the frames with these 0-based indices from `video` (FFmpeg `select`), as PNGs."""
    wanted = sorted(set(indices))
    folder.mkdir(parents=True, exist_ok=True)
    expr = "+".join(f"eq(n\\,{n})" for n in wanted)
    _ffmpeg(
        "-y", "-v", "error", "-i", str(video), "-map", "0:v:0", "-vf", f"select='{expr}'",
        "-fps_mode", "passthrough", str(folder / "ref_%04d.png"),
    )  # fmt: skip
    files = sorted(folder.glob("ref_*.png"))
    assert len(files) == len(wanted), f"decoded {len(files)} reference frames, wanted {wanted}"
    return dict(zip(wanted, files, strict=True))


def image_distance(sample: Path, reference: Path) -> float:
    """Mean absolute RGB difference (0-255) after scaling `sample` to the reference size."""
    with Image.open(sample) as a_file, Image.open(reference) as b_file:
        a, b = a_file.convert("RGB"), b_file.convert("RGB")
    if a.size != b.size:
        a = a.resize(b.size, Image.Resampling.BILINEAR)
    return sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / 3


def console_script() -> str:
    """The installed `scrubgpt-brain` console script (D-063), next to this interpreter."""
    folder = Path(sys.executable).parent
    for name in ("scrubgpt-brain.exe", "scrubgpt-brain"):
        if (folder / name).is_file():
            return str(folder / name)
    found = shutil.which("scrubgpt-brain")
    if not found:
        pytest.fail("the `scrubgpt-brain` console script is not installed (D-063, brain/README.md)")
    return found


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Run `scrubgpt-brain <args>`; never raises on a non-zero exit."""
    return subprocess.run(
        [console_script(), *args],
        capture_output=True,
        timeout=CLI_TIMEOUT_S,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONUTF8": "1"},
    )


def frames_index(out_dir: Path) -> list[dict]:
    """The entries of C1's `frames.json` (brain/README.md: `{"t", "file", "reason"}` sorted by
    time). The README doesn't say whether the top level is a list or `{"frames": [...]}`; both
    are read."""
    data = json.loads((out_dir / "frames.json").read_text(encoding="utf-8"))
    entries = data["frames"] if isinstance(data, dict) else data
    assert isinstance(entries, list), f"frames.json holds no list of frames: {type(entries)}"
    return entries


def files_under(folder: Path) -> dict[str, bytes]:
    """Every file below `folder` (relative POSIX path -> bytes); empty if it doesn't exist."""
    if not folder.exists():
        return {}
    return {
        p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*") if p.is_file()
    }


@pytest.fixture(scope="session")
def media() -> SimpleNamespace:
    """FFmpeg helpers for the B3/C1 tests; skips them when the FFmpeg CLI is missing (#12 AC8)."""
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        pytest.skip(FFMPEG_MISSING)
    return SimpleNamespace(
        make_video=make_video,
        make_audio=make_audio,
        ffprobe=ffprobe,
        streams=streams,
        top_level_boxes=top_level_boxes,
        max_volume_db=max_volume_db,
        decode_image=decode_image,
        reference_frames=reference_frames,
        image_distance=image_distance,
        run_cli=run_cli,
        frames_index=frames_index,
        files_under=files_under,
    )


@pytest.fixture(scope="session")
def case_json_names() -> tuple[str, ...]:
    """The case JSON files of plan §4.2 (D-063: brain/ neither reads nor writes them yet)."""
    return CASE_JSON_NAMES


# ── Block 1 after the tag: CLI runs that need no FFmpeg (reference export, B4 errors, B2) ─────


def run_brain(
    *args: str,
    env: dict[str, str] | None = None,
    drop_env: tuple[str, ...] = (),
    cwd: Path | None = None,
    command: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run `scrubgpt-brain <args>` (or `command`) with `env` added to and `drop_env` removed from
    the environment, in `cwd`; never raises on a non-zero exit. stdout and stderr stay apart."""
    environment = {k: v for k, v in os.environ.items() if k not in drop_env}
    environment.update({"PYTHONUTF8": "1", **(env or {})})
    return subprocess.run(
        command or [console_script(), *args],
        capture_output=True,
        timeout=CLI_TIMEOUT_S,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        cwd=cwd,
    )


def validator_script() -> str:
    """The installed `scrubgpt-validate` console script (contracts, D-052)."""
    folder = Path(sys.executable).parent
    for name in ("scrubgpt-validate.exe", "scrubgpt-validate"):
        if (folder / name).is_file():
            return str(folder / name)
    found = shutil.which("scrubgpt-validate")
    if not found:
        pytest.fail("the `scrubgpt-validate` console script is not installed")
    return found


@pytest.fixture(scope="session")
def cli() -> SimpleNamespace:
    """CLI helpers that need no FFmpeg: `run` (scrubgpt-brain), `validate` (scrubgpt-validate)."""
    return SimpleNamespace(
        run=run_brain,
        validate=lambda *args: run_brain(command=[validator_script(), *args]),
        files_under=files_under,
    )


# ── GraSP-shaped synthetic label files (A6, B1, C8), built from the loaded crosswalk ──────────


class GraspCrosswalk:
    """The A1 GraSP crosswalk of the loaded rule book, sorted into the kinds of label the README
    names (B1 "Mapping", A6 "How it picks"): exact, ambiguous, generic and idle. Every id comes
    from the rule book; none is hard-coded."""

    def __init__(self, book) -> None:
        self.book = book
        self.order = [s.id for p in book.phases for s in p.steps]
        self.steps_of = {p.id: [s.id for s in p.steps] for p in book.phases}
        self.phases = {label.grasp_id: label for label in book.grasp.phases}
        self.steps = {label.grasp_id: label for label in book.grasp.steps}

    def expand(self, targets) -> list[str]:
        found: list[str] = []
        for target in targets:
            for step in self.steps_of.get(target, [target]):
                if step not in found:
                    found.append(step)
        return sorted(found, key=self.order.index)

    def idle_step(self) -> int:
        return next(g for g, lab in self.steps.items() if lab.maps_to == () and not lab.by_phase)

    def idle_phase(self) -> int:
        return next(g for g, lab in self.phases.items() if lab.maps_to == ())

    def a_phase_for(self, step_id: str) -> int:
        for g, lab in self.phases.items():
            if lab.maps_to != "phase" and step_id in self.expand(lab.maps_to):
                return g
        return next(g for g, lab in self.phases.items() if lab.maps_to)

    def exact(self) -> list[tuple[int, str]]:
        """(GraSP step, rule-book step) of labels whose `maps_to` names exactly one step."""
        found = []
        for g, lab in self.steps.items():
            if lab.by_phase or lab.maps_to == "phase" or len(lab.maps_to) != 1:
                continue
            if lab.maps_to[0] in self.order:
                found.append((g, lab.maps_to[0]))
        return found

    def exact_steps(self) -> list[str]:
        return sorted({s for _, s in self.exact()}, key=self.order.index)

    def label_for(self, step_id: str) -> int:
        return next(g for g, s in self.exact() if s == step_id)

    def ambiguous(self) -> list[tuple[int, list[str]]]:
        """(GraSP step, candidate steps) of labels naming several steps (no `by_phase`)."""
        found = []
        for g, lab in self.steps.items():
            if lab.by_phase or lab.maps_to == "phase":
                continue
            candidates = self.expand(lab.maps_to)
            if len(candidates) >= 2:
                found.append((g, candidates))
        return found

    def generic(self) -> list[int]:
        """GraSP steps of generic acts (`maps_to: phase`, no `by_phase`)."""
        return [g for g, lab in self.steps.items() if lab.maps_to == "phase" and not lab.by_phase]

    def single_target_phases(self) -> list[tuple[int, str]]:
        """(GraSP phase, rule-book step) of GraSP phases that map to exactly one step."""
        found = []
        for g, lab in self.phases.items():
            if lab.maps_to in ((), "phase"):
                continue
            targets = self.expand(lab.maps_to)
            if len(targets) == 1:
                found.append((g, targets[0]))
        return found


def write_grasp_file(path: Path, raw_grasp: dict, cases: dict, *, spacing: int = 1,
                     start: int = 0) -> Path:  # fmt: skip
    """A GraSP long-term file (README B1 "Input"): the crosswalk's categories (`name` = code,
    `description` = name), and per case one image (`id`, `video_name`, `frame_num`) and one
    annotation (`image_id`, `phases`, `steps`) per label, `spacing` frames apart."""
    data = {
        "phases_categories": [
            {"id": c["grasp_id"], "name": c["code"], "description": c["name"]}
            for c in raw_grasp["phases"]
        ],
        "steps_categories": [
            {"id": c["grasp_id"], "name": c["code"], "description": c["name"]}
            for c in raw_grasp["steps"]
        ],
        "images": [],
        "annotations": [],
    }
    for case, labels in cases.items():
        for k, (phase, step) in enumerate(labels):
            image_id = len(data["images"]) + 1
            frame = start + k * spacing
            data["images"].append({
                "id": image_id, "file_name": f"{case}/{frame:09d}.jpg", "width": 1280,
                "height": 800, "video_name": case, "frame_num": frame,
            })  # fmt: skip
            data["annotations"].append(
                {"id": image_id, "image_id": image_id, "phases": phase, "steps": step}
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.fixture(scope="session")
def grasp(rulebook) -> SimpleNamespace:
    """Synthetic GraSP label files from the committed crosswalk (no real GraSP data)."""
    from scrubgpt_brain.engines.rulebook import load_knowledge

    cw = GraspCrosswalk(load_knowledge().rulebook)
    return SimpleNamespace(
        cw=cw,
        write=lambda path, cases, **kw: write_grasp_file(path, rulebook["grasp"], cases, **kw),
        idle=lambda n: [(cw.idle_phase(), cw.idle_step())] * n,
        exact=lambda step_id, n: [(cw.a_phase_for(step_id), cw.label_for(step_id))] * n,
    )
