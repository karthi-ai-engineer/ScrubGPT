"""B2 YouTube importer (plan §2.2): a YouTube RARP video → its metadata, a suggested registry
entry for B4, and the source video that B3 normalises.

The demo uses 10–12 public YouTube RARP videos (plan §7: about 6 narrated in English, about 4 in
Japanese, 1–2 without narration), for private internal demo use only (D-003). For each one:
- `fetch_metadata(url)` reads yt-dlp's metadata without downloading anything (`VideoMeta`).
- `suggest_entry(meta, case_id)` turns it into a **suggested** registry entry (every
  `REGISTRY_FIELDS` key, in that order) plus the list of fields it is unsure of:
  - `language`: yt-dlp's spoken language if it is `ja` or `en`. Otherwise a guess from the title
    and description: Japanese kana or kanji → `ja`, else `en` (unsure). No audio → `none`.
  - `narrated`: true with audio, a `ja`/`en` language and narration wording in the title or
    description (`NARRATION_WORDS`: "narrated", "commentary", "explained", 解説, ナレーション, …).
    Otherwise false, and unsure, except without audio: a silent video has no narration.
  - `video_type`: `edited` under `EDITED_UNDER_S` (45 min: a full-length RARP takes about
    1.5–3 h) or with editing wording (`EDITING_WORDS`: "edited", "condensed", "highlights", 要約,
    ダイジェスト, …). Otherwise `full`, unsure under `FULL_FROM_S` (90 min) or without a duration.
    When in doubt, `edited` is the safe value: it only switches off duration deviations (E2),
    while a wrong `full` makes false ones.
  - `title`: the original title in both halves. The half in the other language starts with
    `TRANSLATE_MARK` until a person translates it, so `title` is always listed as unsure.
  - `source: youtube`, `source_url` (the video's page), `synthetic_speech: false`,
    `default_step_track: ai` and `data_note: null`, so B4 uses the default YouTube note.
- `download(url, out_dir)` downloads the best video and audio up to 1080 px high, merged to MP4,
  as `out_dir/source.mp4` (`.webm`, … only when one file needed no merge). B3 normalises it.

**A person always reviews a suggestion before it goes into the registry.** It is guessed from the
words of the title and of the first `DESCRIPTION_CHARS` characters of the description, and from
the duration, never from watching or hearing the video. The reviewer watches the video, settles
the unsure fields, translates the title and only then adds the entry to the registry, where B4
checks it against the contract.

yt-dlp is imported on first use: it is large, and the other stages don't need it. Every yt-dlp
failure (network, a removed or private video, an age gate, the FFmpeg merge) raises `MediaError`
with yt-dlp's reason. Age-restricted videos (many surgical videos are) need the cookies of a
signed-in browser: `cookie_file`, a Netscape `cookies.txt`, which holds a login, so it stays out
of git. yt-dlp needs a JavaScript runtime for YouTube; deno and Node.js are both enabled.

Nothing half-written is left behind: yt-dlp downloads into `source.part/` in `out_dir`, and the
finished file is moved into place. On failure that folder is removed and an earlier `source.*` is
not touched. Case JSON files are not this stage's job (B4 writes `case.json`).
"""

import os
import re
import shutil
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Self

import yaml
from scrubgpt_contracts.models.common import CASE_ID_PATTERN

from scrubgpt_brain.engines.media import MediaError, tool
from scrubgpt_brain.pipeline.cases import REGISTRY_FIELDS

SOURCE_STEM = "source"
VIDEO_SUFFIXES = (".mp4", ".webm", ".mkv", ".mov")
"""What a finished download can be called (`source.mp4` unless one file needed no merge)."""
WORK_DIR = "source.part"
MAX_HEIGHT = 1080
"""Enough for B3's 720 px and for GPT vision frames, without fetching 4K."""
DESCRIPTION_CHARS = 500
"""How much of the description `VideoMeta` keeps: the summary and the key words come first."""
EDITED_UNDER_S = 45 * 60
"""A video shorter than this is `edited`: a full-length RARP takes about 1.5–3 h."""
FULL_FROM_S = 90 * 60
"""A video at least this long, with no editing wording, is `full` and sure; a shorter one (or one
without a duration) is `full` but unsure."""
NARRATION_WORDS = re.compile(
    r"\b(?:narrat|commentar|explain|explanation|voice[- ]?over|lecture|talks? through)"
    r"|解説|ナレーション|実況|講義|音声付",
    re.IGNORECASE,
)
"""Wording that suggests someone talks over the video (Japanese words have no word boundaries)."""
EDITING_WORDS = re.compile(
    r"\b(?:edited|condensed|highlights?|abridged|shortened|digest|time[- ]?lapse|sped[- ]up"
    r"|fast[- ]forward\w*|key steps|short version)\b"
    r"|要約|ダイジェスト|編集版|短縮|ハイライト|抜粋|早送り",
    re.IGNORECASE,
)
"""Wording that says the video was cut down ("unedited" doesn't match)."""
TRANSLATE_MARK = {"ja": "【要翻訳】", "en": "[to translate] "}
"""Starts the half of a suggested title that is still a copy of the original."""
_JAPANESE = re.compile(r"[぀-ヿㇰ-ㇿ㐀-䶿一-鿿ｦ-ﾟ]")
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


class YoutubeDLLike(Protocol):
    """What B2 uses of `yt_dlp.YoutubeDL`; tests pass a stub."""

    def __enter__(self) -> Self: ...

    def __exit__(self, *exc_info: object) -> object: ...

    def extract_info(self, url: str, download: bool = True) -> Any: ...

    def process_ie_result(self, ie_result: Any, download: bool = True) -> Any: ...


YdlFactory = Callable[[dict[str, Any]], YoutubeDLLike]
"""Makes a `YoutubeDL`-like object from yt-dlp options."""


def youtube_dl(options: dict[str, Any]) -> YoutubeDLLike:
    """`yt_dlp.YoutubeDL(options)`, the default `ydl_factory`. yt-dlp is imported here, on first
    use: it is large, and the other stages and commands don't need it."""
    try:
        import yt_dlp
    except ImportError:
        raise MediaError("yt-dlp isn't installed: run `uv sync --all-packages`") from None
    return yt_dlp.YoutubeDL(options)


@dataclass(frozen=True)
class VideoMeta:
    """What yt-dlp says about one video, read without downloading it."""

    url: str
    """The video's page (yt-dlp's `webpage_url`), else the URL given."""
    video_id: str
    title: str
    channel: str | None
    duration_s: float | None
    """None when yt-dlp doesn't know it."""
    upload_date: str | None
    """`YYYY-MM-DD`."""
    language: str | None
    """The spoken language yt-dlp reports (e.g. `en`, `ja`, `en-US`): the video's `language`, else
    that of its preferred audio format; None if it reports none."""
    has_audio: bool
    """True if any format has an audio codec other than `none`."""
    chapters: tuple[tuple[float, str], ...]
    """`(start_s, title)` of each chapter, in order."""
    description: str
    """The first `DESCRIPTION_CHARS` characters of the description."""
    license: str | None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _has_codec(codec: Any) -> bool:
    return isinstance(codec, str) and codec not in ("", "none")


def _audio_language(audio_formats: Sequence[Mapping[str, Any]]) -> str | None:
    tagged = [f for f in audio_formats if f.get("language")]
    if not tagged:
        return None

    def rank(f: Mapping[str, Any]) -> float:  # yt-dlp ranks a dubbed video's original track first
        preference = _number(f.get("language_preference"))
        return float("-inf") if preference is None else preference

    return str(max(tagged, key=rank)["language"])


def _iso_date(value: Any) -> str | None:
    text = str(value or "")
    if re.fullmatch(r"\d{8}", text):
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text or None


def meta_from_info(info: Any, url: str) -> VideoMeta:
    """A `VideoMeta` from a yt-dlp info dict (`extract_info(url, download=False)`, or the JSON of
    `yt-dlp --dump-json`). Raises `MediaError` if it isn't one finished video (a playlist, a
    channel, a live or upcoming stream) or has no id or title."""
    if not isinstance(info, Mapping):
        raise MediaError(f"yt-dlp found no video at {url}")
    kind = info.get("_type")
    if kind in ("playlist", "multi_video"):
        raise MediaError(f"{url} is a {kind}, not one video: give the URL of one video")
    if info.get("live_status") in ("is_live", "is_upcoming"):
        raise MediaError(f"{url} is a live or upcoming stream: import it once it has ended")
    video_id = str(info.get("id") or "").strip()
    title = " ".join(str(info.get("title") or "").split())
    if not video_id or not title:
        raise MediaError(f"yt-dlp gave no video id or title for {url}")
    formats = [f for f in info.get("formats") or [info] if isinstance(f, Mapping)]
    audio = [f for f in formats if _has_codec(f.get("acodec"))]
    duration = _number(info.get("duration"))
    chapters = sorted(
        (start, " ".join(str(chapter.get("title") or "").split()))
        for chapter in info.get("chapters") or ()
        if isinstance(chapter, Mapping)
        and (start := _number(chapter.get("start_time"))) is not None
    )
    return VideoMeta(
        url=str(info.get("webpage_url") or url),
        video_id=video_id,
        title=title,
        channel=str(info.get("channel") or info.get("uploader") or "") or None,
        duration_s=duration if duration and duration > 0 else None,
        upload_date=_iso_date(info.get("upload_date")),
        language=str(info.get("language") or "") or _audio_language(audio),
        has_audio=bool(audio),
        chapters=tuple(chapters),
        description=str(info.get("description") or "")[:DESCRIPTION_CHARS].rstrip(),
        license=str(info.get("license") or "") or None,
    )


def _reason(exc: BaseException) -> str:
    text = _ANSI.sub("", str(exc)).strip().removeprefix("ERROR:").strip()
    return text or type(exc).__name__


@contextmanager
def _yt_dlp_errors(what: str) -> Iterator[None]:
    """Turns a yt-dlp failure into `MediaError(f"{what}: <yt-dlp's reason>")`."""
    try:
        yield
    except MediaError:
        raise
    except Exception as exc:  # yt-dlp raises many types: DownloadError, ExtractorError, OSError …
        raise MediaError(f"{what}: {_reason(exc)}") from None


def _options(cookie_file: Path | None) -> dict[str, Any]:
    options: dict[str, Any] = {
        "quiet": True,  # stdout carries the CLI's YAML; yt-dlp's warnings still go to stderr
        "noprogress": True,
        "noplaylist": True,  # a watch URL with `&list=…` means that one video
        "js_runtimes": {"deno": {}, "node": {}},
    }
    if cookie_file is not None:
        if not cookie_file.is_file():
            raise MediaError(f"cookie file not found: {cookie_file}")
        options["cookiefile"] = str(cookie_file)
    return options


def fetch_metadata(
    url: str, *, ydl_factory: YdlFactory | None = None, cookie_file: Path | None = None
) -> VideoMeta:
    """The metadata of the video at `url`, read without downloading it. `ydl_factory` defaults to
    `youtube_dl` (`yt_dlp.YoutubeDL`).

    Raises `MediaError` if yt-dlp fails (network, a removed or private video, an age gate: pass
    `cookie_file`) or the URL isn't one video.
    """
    options = _options(cookie_file)
    with _yt_dlp_errors(f"yt-dlp could not read {url}"):
        with (ydl_factory or youtube_dl)(options) as ydl:
            info = ydl.extract_info(url, download=False)
    return meta_from_info(info, url)


def _primary(language: str | None) -> str | None:
    """`en-US` → `en`."""
    return re.split(r"[-_]", language.strip().lower())[0] if language else None


def suggest_entry(meta: VideoMeta, case_id: str) -> tuple[dict[str, Any], list[str]]:
    """A suggested registry entry for the video (every `REGISTRY_FIELDS` key, in that order) and
    the names of the fields a person must still settle (`unsure`, in the same order), by the rules
    in the module docstring. Raises `ValueError` for an invalid case id.

    **A person always reviews the suggestion before it goes into the registry.**
    """
    if not re.match(CASE_ID_PATTERN, case_id):
        raise ValueError(
            f"{case_id!r} isn't a case id: lower-case letters and digits in groups joined by "
            "hyphens, e.g. yt-ja-01"
        )
    text = f"{meta.title}\n{meta.description}"
    unsure = {"title"}

    spoken = _primary(meta.language)
    if not meta.has_audio:
        language = "none"
    elif spoken in ("ja", "en"):
        language = spoken
    else:
        language = "ja" if _JAPANESE.search(text) else "en"
        unsure.add("language")

    narrated = language != "none" and NARRATION_WORDS.search(text) is not None
    if language != "none" and not narrated:
        unsure.add("narrated")

    duration = meta.duration_s
    if EDITING_WORDS.search(text) or (duration is not None and duration < EDITED_UNDER_S):
        video_type = "edited"
    else:
        video_type = "full"
        if duration is None or duration < FULL_FROM_S:
            unsure.add("video_type")

    original = "ja" if _JAPANESE.search(meta.title) else "en"
    title = {
        lang: meta.title if lang == original else TRANSLATE_MARK[lang] + meta.title
        for lang in ("ja", "en")
    }
    values: dict[str, Any] = {
        "id": case_id,
        "title": title,
        "source": "youtube",
        "source_url": meta.url,
        "language": language,
        "video_type": video_type,
        "narrated": narrated,
        "synthetic_speech": False,
        "default_step_track": "ai",
        "data_note": None,
    }
    entry = {field: values[field] for field in REGISTRY_FIELDS}
    return entry, [field for field in REGISTRY_FIELDS if field in unsure]


def _clock(seconds: float | None) -> str:
    if seconds is None:
        return "unknown duration"
    s = round(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def suggestion_yaml(meta: VideoMeta, entry: Mapping[str, Any], unsure: Sequence[str]) -> str:
    """The suggestion as YAML to paste into the registry (a list of one entry), headed by comments:
    the video's facts and the unsure fields."""
    audio = f"audio, yt-dlp language {meta.language or 'unknown'}" if meta.has_audio else "no audio"
    facts = [
        _clock(meta.duration_s),
        audio,
        f"{len(meta.chapters)} chapter(s)",
        f"channel {meta.channel or 'unknown'}",
        f"uploaded {meta.upload_date or 'unknown'}",
        f"license {meta.license or 'unknown'}",
    ]
    lines = [
        f"# Suggested registry entry for {entry['id']}, guessed from yt-dlp's metadata: a person",
        "# reviews it (watches the video, translates the title) before it goes into the registry.",
        f"# {meta.title}",
        f"# {', '.join(facts)}",
        f"# unsure: {', '.join(unsure) if unsure else '(none)'}",
        yaml.safe_dump([dict(entry)], allow_unicode=True, sort_keys=False, width=100).rstrip(),
    ]
    return "\n".join(lines)


def _remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


def _finished_file(work: Path, url: str) -> Path:
    """The file yt-dlp finished in `work`: `source.<ext>`, not a `source.f137.mp4` part."""
    done = [
        p
        for p in work.iterdir()
        if p.is_file() and p.stem == SOURCE_STEM and p.suffix.lower() in VIDEO_SUFFIXES
    ]
    if len(done) != 1:
        found = ", ".join(sorted(p.name for p in work.iterdir())) or "nothing"
        raise MediaError(f"yt-dlp didn't leave one finished video for {url} (found {found})")
    return done[0]


def download(
    url: str,
    out_dir: Path,
    *,
    ydl_factory: YdlFactory | None = None,
    max_height: int = MAX_HEIGHT,
    cookie_file: Path | None = None,
) -> Path:
    """Download the video at `url` into `out_dir` and return its path: `source.mp4`, the best video
    up to `max_height` px high and the best audio, merged by FFmpeg. A video without audio gives a
    video-only file. `ydl_factory` defaults to `youtube_dl` (`yt_dlp.YoutubeDL`).

    Raises `ValueError` for a bad `max_height`, and `MediaError` if FFmpeg isn't installed, the URL
    isn't one video or yt-dlp fails. Then no new `source.*` is left in `out_dir`, and an earlier
    one is not touched. A successful run replaces an earlier `source.*`.
    """
    if max_height <= 0:
        raise ValueError(f"max_height must be positive, not {max_height}")
    ffmpeg = tool("ffmpeg")  # yt-dlp merges video and audio with it
    limit = f"[height<={max_height}]"
    work = out_dir / WORK_DIR
    options = {
        **_options(cookie_file),
        # Best video + best audio; else one file with both; else video only (a silent video).
        "format": f"bv*{limit}+ba/b{limit}/bv*{limit}",
        "merge_output_format": "mp4",
        "ffmpeg_location": ffmpeg,
        "paths": {"home": str(work), "temp": str(work)},
        "outtmpl": {"default": f"{SOURCE_STEM}.%(ext)s"},
        "overwrites": True,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    _remove(work)
    work.mkdir()
    try:
        with _yt_dlp_errors(f"yt-dlp could not download {url}"):
            with (ydl_factory or youtube_dl)(options) as ydl:
                info = ydl.extract_info(url, download=False)
                meta_from_info(info, url)  # one finished video, before anything is downloaded
                ydl.process_ie_result(info, download=True)
        finished = _finished_file(work, url)
        target = out_dir / f"{SOURCE_STEM}{finished.suffix.lower()}"
        os.replace(finished, target)
    finally:
        _remove(work)
    for suffix in VIDEO_SUFFIXES:
        if suffix != target.suffix:
            (out_dir / f"{SOURCE_STEM}{suffix}").unlink(missing_ok=True)
    return target
