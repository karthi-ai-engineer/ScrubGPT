"""Dev1's unit tests for B2, the YouTube importer (plan §2.2).

Offline: yt-dlp is replaced by a stub that returns saved info dicts (shaped like yt-dlp's
`extract_info(url, download=False)`) and "downloads" by writing a small file where yt-dlp would.
Nothing here contacts YouTube or needs yt-dlp installed.
"""

import copy
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml
from scrubgpt_brain import cli
from scrubgpt_brain.engines.media import MediaError
from scrubgpt_brain.pipeline import youtube as yt
from scrubgpt_brain.pipeline.cases import (
    DEFAULT_DATA_NOTES,
    REGISTRY_FIELDS,
    build_case,
    load_registry,
)

URL = "https://www.youtube.com/watch?v=abc123XYZ00&list=PLsomething"
PAGE = "https://www.youtube.com/watch?v=abc123XYZ00"
FAKE_VIDEO = b"\x00\x00\x00\x18ftypmp42 a stand-in for a video"

STORYBOARD = {"format_id": "sb0", "ext": "mhtml", "vcodec": "none", "acodec": "none"}
VIDEO_ONLY = {"format_id": "137", "ext": "mp4", "vcodec": "avc1.640028", "acodec": "none"}
AUDIO_EN = {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2"}
AUDIO_JA = {**AUDIO_EN, "language": "ja", "language_preference": -1}


def info(**changes: Any) -> dict[str, Any]:
    """A saved yt-dlp info dict for one public video (an English 2 h full case by default)."""
    base: dict[str, Any] = {
        "_type": "video",
        "id": "abc123XYZ00",
        "title": "Robotic radical prostatectomy: complete case",
        "channel": "Urology Teaching",
        "uploader": "Urology Teaching",
        "duration": 2 * 3600 + 5,
        "upload_date": "20240501",
        "webpage_url": PAGE,
        "description": "Robot-assisted radical prostatectomy with the da Vinci Xi.",
        "language": None,
        "license": None,
        "chapters": None,
        "live_status": "not_live",
        "formats": [STORYBOARD, VIDEO_ONLY, AUDIO_EN],
    }
    base.update(changes)
    return base


JA_NARRATED = info(
    title="ロボット支援前立腺全摘除術 手術解説",
    description="泌尿器科の手術動画です。",
    duration=2 * 3600 + 40 * 60,
    formats=[STORYBOARD, VIDEO_ONLY, AUDIO_JA],
)
EN_NARRATED = info(title="Full narrated robotic-assisted prostatectomy", language="en-US")
EN_HIGHLIGHTS = info(title="RARP highlights: bladder neck and anastomosis", duration=20 * 60)
SILENT = info(title="Robotic prostatectomy, narrated in captions", formats=[VIDEO_ONLY])
EN_UNTOLD = info(language="en")


class DownloadError(Exception):
    """Stands in for `yt_dlp.utils.DownloadError` (its messages start with `ERROR:`)."""


class StubYDL:
    """A stand-in for `yt_dlp.YoutubeDL`, made with the options B2 passes."""

    def __init__(self, options: dict[str, Any], info: dict[str, Any], fail: str | None, ext: str):
        self.options, self.info, self.fail, self.ext = options, info, fail, ext
        self.downloaded = False

    def __enter__(self) -> "StubYDL":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def extract_info(self, url: str, download: bool = True) -> dict[str, Any]:
        assert not download, "B2 reads metadata first, then downloads with process_ie_result"
        if self.fail == "extract":
            raise DownloadError(f"ERROR: [youtube] {url}: Video unavailable")
        return copy.deepcopy(self.info)

    def process_ie_result(self, ie_result: dict[str, Any], download: bool = True) -> Any:
        """Writes what yt-dlp would: a part file, then `source.<ext>` once merged."""
        self.downloaded = True
        home = Path(self.options["paths"]["home"])
        stem = self.options["outtmpl"]["default"].removesuffix(".%(ext)s")
        part = home / f"{stem}.f137.mp4.part"
        part.write_bytes(FAKE_VIDEO[:10])
        if self.fail == "download":
            raise DownloadError("ERROR: unable to download video data: HTTP Error 403: Forbidden")
        part.unlink()
        (home / f"{stem}.{self.ext}").write_bytes(FAKE_VIDEO)
        return ie_result


class StubFactory:
    """`ydl_factory` for the tests; keeps every stub it made."""

    def __init__(self, info: dict[str, Any], *, fail: str | None = None, ext: str = "mp4"):
        self.info, self.fail, self.ext = info, fail, ext
        self.made: list[StubYDL] = []

    def __call__(self, options: dict[str, Any]) -> StubYDL:
        self.made.append(StubYDL(options, self.info, self.fail, self.ext))
        return self.made[-1]


@pytest.fixture
def ffmpeg(monkeypatch) -> None:
    """`download` looks FFmpeg up for yt-dlp's merge; the stub doesn't need it (nor does CI)."""
    monkeypatch.setattr(yt, "tool", lambda name: name)


def suggest(saved: dict[str, Any], case_id: str = "yt-en-01"):
    meta = yt.fetch_metadata(URL, ydl_factory=StubFactory(saved))
    entry, unsure = yt.suggest_entry(meta, case_id)
    return meta, entry, unsure


# ── metadata ──────────────────────────────────────────────────────────────────


def test_metadata_parses_chapters_audio_duration_and_the_rest():
    chapters = [
        {"start_time": 600.0, "end_time": 1800.0, "title": "Bladder neck"},
        {"start_time": 0.0, "end_time": 600.0, "title": "  Port   placement "},
        {"start_time": "bad", "title": "skipped"},
    ]
    saved = info(
        channel=None,
        chapters=chapters,
        description="x" * 600,
        license="Creative Commons Attribution license (reuse allowed)",
        formats=[
            STORYBOARD,
            VIDEO_ONLY,
            {**AUDIO_EN, "language": "en"},
            AUDIO_JA | {"language_preference": 10},
        ],
    )
    factory = StubFactory(saved)
    meta = yt.fetch_metadata(URL, ydl_factory=factory)
    assert meta == yt.VideoMeta(
        url=PAGE,  # the video's page, without the playlist part of the URL given
        video_id="abc123XYZ00",
        title="Robotic radical prostatectomy: complete case",
        channel="Urology Teaching",  # from `uploader` when `channel` is missing
        duration_s=7205.0,
        upload_date="2024-05-01",
        language="ja",  # the audio format yt-dlp ranks first (a dubbed video's original track)
        has_audio=True,
        chapters=((0.0, "Port placement"), (600.0, "Bladder neck")),
        description="x" * yt.DESCRIPTION_CHARS,
        license="Creative Commons Attribution license (reuse allowed)",
    )
    options = factory.made[0].options
    assert options["noplaylist"] and options["quiet"] and "deno" in options["js_runtimes"]


def test_audio_detection_ignores_formats_without_an_audio_codec():
    formats = [STORYBOARD, VIDEO_ONLY, {**VIDEO_ONLY, "acodec": None}]
    meta = yt.meta_from_info(info(formats=formats), URL)
    assert not meta.has_audio and meta.language is None
    assert yt.meta_from_info(info(formats=[]), URL).has_audio is False  # no codec at the top
    assert yt.meta_from_info(info(duration=None), URL).duration_s is None


def test_a_yt_dlp_error_becomes_a_media_error_with_its_reason():
    with pytest.raises(MediaError, match=r"could not read .*: \[youtube\] .*Video unavailable"):
        yt.fetch_metadata(URL, ydl_factory=StubFactory(info(), fail="extract"))


@pytest.mark.parametrize(
    "saved",
    [
        {"_type": "playlist", "id": "PL1", "title": "RARP videos", "entries": []},
        info(live_status="is_upcoming"),
        info(title=" "),
        None,
    ],
)
def test_anything_but_one_finished_video_is_refused(saved):
    with pytest.raises(MediaError):
        yt.fetch_metadata(URL, ydl_factory=StubFactory(saved))


def test_missing_yt_dlp_or_cookie_file_is_a_media_error(monkeypatch, tmp_path: Path):
    monkeypatch.setitem(sys.modules, "yt_dlp", None)  # `import yt_dlp` now fails
    with pytest.raises(MediaError, match="yt-dlp isn't installed"):
        yt.fetch_metadata(URL)
    with pytest.raises(MediaError, match="cookie file not found"):
        yt.fetch_metadata(URL, ydl_factory=StubFactory(info()), cookie_file=tmp_path / "no.txt")


def test_a_cookie_file_is_passed_to_yt_dlp(tmp_path: Path):
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    factory = StubFactory(info())
    yt.fetch_metadata(URL, ydl_factory=factory, cookie_file=cookies)
    assert factory.made[0].options["cookiefile"] == str(cookies)


# ── suggest_entry ─────────────────────────────────────────────────────────────


def test_a_japanese_narrated_video_is_ja_and_narrated():
    meta, entry, unsure = suggest(JA_NARRATED, "yt-ja-01")
    assert tuple(entry) == REGISTRY_FIELDS
    assert (entry["language"], entry["narrated"], entry["video_type"]) == ("ja", True, "full")
    assert entry["title"] == {
        "ja": "ロボット支援前立腺全摘除術 手術解説",
        "en": yt.TRANSLATE_MARK["en"] + "ロボット支援前立腺全摘除術 手術解説",
    }
    assert entry["source"] == "youtube" and entry["source_url"] == PAGE
    assert (entry["synthetic_speech"], entry["default_step_track"]) == (False, "ai")
    assert entry["data_note"] is None
    assert unsure == ["title"]  # the English half still needs a translation


def test_an_english_two_hour_video_is_en_and_full():
    _, entry, unsure = suggest(EN_NARRATED)
    assert (entry["language"], entry["video_type"], entry["narrated"]) == ("en", "full", True)
    assert entry["title"]["en"] == "Full narrated robotic-assisted prostatectomy"
    assert entry["title"]["ja"].startswith(yt.TRANSLATE_MARK["ja"])
    assert unsure == ["title"]


@pytest.mark.parametrize(
    ("title", "duration", "video_type", "type_unsure"),
    [
        ("RARP highlights: bladder neck and anastomosis", 20 * 60, "edited", False),
        ("RARP: bladder neck and anastomosis", 20 * 60, "edited", False),  # too short to be full
        ("Robotic prostatectomy, condensed", 2 * 3600, "edited", False),
        ("ロボット支援前立腺全摘除術 ダイジェスト", 2 * 3600, "edited", False),
        ("Unedited robotic prostatectomy", 2 * 3600, "full", False),
        ("Robotic prostatectomy", 60 * 60, "full", True),  # long, but shorter than a full case
        ("Robotic prostatectomy", None, "full", True),
    ],
)
def test_video_type_from_duration_and_wording(title, duration, video_type, type_unsure):
    _, entry, unsure = suggest(info(title=title, duration=duration))
    assert entry["video_type"] == video_type
    assert ("video_type" in unsure) is type_unsure


def test_a_twenty_minute_highlights_video_is_edited():
    _, entry, unsure = suggest(EN_HIGHLIGHTS)
    assert entry["video_type"] == "edited" and "video_type" not in unsure


def test_a_video_without_audio_is_language_none_and_not_narrated():
    _, entry, unsure = suggest(SILENT)
    assert (entry["language"], entry["narrated"]) == ("none", False)  # despite "narrated"
    assert unsure == ["title"]  # no audio is certain: no language or narration to doubt


def test_unsure_lists_narration_that_cant_be_told():
    _, entry, unsure = suggest(EN_UNTOLD)
    assert (entry["language"], entry["narrated"]) == ("en", False)
    assert unsure == ["title", "narrated"]


@pytest.mark.parametrize(
    ("language", "description", "guess"),
    [
        (None, "泌尿器科の手術動画です。", "ja"),  # no language from yt-dlp: the script decides
        ("fr", "Prostatectomie robotique.", "en"),  # not ja/en: still a guess
    ],
)
def test_language_is_guessed_from_the_script_and_marked_unsure(language, description, guess):
    saved = info(language=language, description=description, formats=[VIDEO_ONLY, AUDIO_EN])
    _, entry, unsure = suggest(saved)
    assert entry["language"] == guess and "language" in unsure


def test_an_invalid_case_id_is_a_value_error():
    meta = yt.meta_from_info(info(), URL)
    with pytest.raises(ValueError, match="isn't a case id"):
        yt.suggest_entry(meta, "YT_JA_01")


@pytest.mark.parametrize("saved", [JA_NARRATED, EN_NARRATED, EN_HIGHLIGHTS, SILENT, EN_UNTOLD])
def test_the_suggestion_passes_the_contract_once_a_duration_is_added(saved):
    meta, entry, _ = suggest(saved, "yt-en-03")
    case = build_case(entry, meta.duration_s)
    assert case.id == "yt-en-03" and case.duration_s == meta.duration_s
    assert case.data_note.en == DEFAULT_DATA_NOTES["youtube"]["en"]


# ── download ──────────────────────────────────────────────────────────────────


def test_download_moves_the_finished_file_into_place(ffmpeg, tmp_path: Path):
    out = tmp_path / "work" / "yt-en-01"
    factory = StubFactory(info())
    path = yt.download(URL, out, ydl_factory=factory)
    assert path == out / "source.mp4" and path.read_bytes() == FAKE_VIDEO
    assert [p.name for p in out.iterdir()] == ["source.mp4"]  # no source.part/ left
    stub = factory.made[0]
    assert stub.downloaded
    assert stub.options["format"] == "bv*[height<=1080]+ba/b[height<=1080]/bv*[height<=1080]"
    assert stub.options["merge_output_format"] == "mp4"
    assert stub.options["paths"]["home"] == str(out / yt.WORK_DIR)
    assert stub.options["ffmpeg_location"] == "ffmpeg"


def test_a_re_run_replaces_the_earlier_download(ffmpeg, tmp_path: Path):
    yt.download(URL, tmp_path, ydl_factory=StubFactory(info()))
    factory = StubFactory(info(), ext="webm")
    path = yt.download(URL, tmp_path, ydl_factory=factory, max_height=720)
    assert path == tmp_path / "source.webm"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["source.webm"]
    assert "[height<=720]" in factory.made[0].options["format"]


def test_a_failed_download_leaves_no_file_and_keeps_the_earlier_one(ffmpeg, tmp_path: Path):
    fresh = tmp_path / "fresh"
    with pytest.raises(MediaError, match="could not download .*HTTP Error 403"):
        yt.download(URL, fresh, ydl_factory=StubFactory(info(), fail="download"))
    assert list(fresh.iterdir()) == []

    kept = tmp_path / "kept"
    kept.mkdir()
    (kept / "source.mp4").write_bytes(b"earlier download")
    with pytest.raises(MediaError):
        yt.download(URL, kept, ydl_factory=StubFactory(info(), fail="download"))
    assert [p.name for p in kept.iterdir()] == ["source.mp4"]
    assert (kept / "source.mp4").read_bytes() == b"earlier download"


def test_a_playlist_is_refused_before_anything_is_downloaded(ffmpeg, tmp_path: Path):
    factory = StubFactory({"_type": "playlist", "id": "PL1", "title": "RARP", "entries": []})
    with pytest.raises(MediaError, match="playlist"):
        yt.download(URL, tmp_path, ydl_factory=factory)
    assert not factory.made[0].downloaded and list(tmp_path.iterdir()) == []


def test_a_bad_max_height_is_a_value_error(ffmpeg, tmp_path: Path):
    with pytest.raises(ValueError):
        yt.download(URL, tmp_path, ydl_factory=StubFactory(info()), max_height=0)


# ── CLI ───────────────────────────────────────────────────────────────────────


def test_cli_prints_a_registry_entry_as_yaml(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(yt, "youtube_dl", StubFactory(JA_NARRATED))
    lines: list[str] = []
    assert cli.main(["youtube", URL, "--case-id", "yt-ja-02"], out=lines.append) == 0
    text = "\n".join(lines)
    assert "# unsure: title" in text and "ロボット支援前立腺全摘除術" in text  # readable, not \u…
    [entry] = yaml.safe_load(text)
    assert entry["id"] == "yt-ja-02" and entry["language"] == "ja" and entry["narrated"] is True
    registry = tmp_path / "registry.yaml"  # what the reviewer pastes it into
    registry.write_text(text + "\n", encoding="utf-8")
    assert build_case(load_registry(registry)["yt-ja-02"], 9600.0).title.ja.endswith("手術解説")


def test_cli_downloads_with_download(monkeypatch, ffmpeg, tmp_path: Path):
    monkeypatch.setattr(yt, "youtube_dl", StubFactory(info()))
    lines: list[str] = []
    args = ["youtube", URL, "--case-id", "yt-en-01", "--download", str(tmp_path / "src")]
    assert cli.main(args, out=lines.append) == 0
    assert (tmp_path / "src" / "source.mp4").read_bytes() == FAKE_VIDEO
    assert lines[-1].startswith("# downloaded ")


@pytest.mark.parametrize(
    ("factory", "case_id"),
    [(StubFactory(info(), fail="extract"), "yt-en-01"), (StubFactory(info()), "Not An Id")],
)
def test_cli_exits_1_on_an_error(monkeypatch, factory, case_id):
    monkeypatch.setattr(yt, "youtube_dl", factory)
    lines: list[str] = []
    assert cli.main(["youtube", URL, "--case-id", case_id], out=lines.append, err=lines.append) == 1
    assert lines[-1].startswith("scrubgpt-brain: error:")
