"""B2 YouTube importer: criteria B2-1 to B2-4 of the T1 brief at 5a89091 (plan §2.2 B2;
brain/README.md "B2 YouTube importer"; the CLI docstring). **No network, ever**: yt-dlp is
replaced by stubs (`ydl_factory`) fed with saved, synthetic info dicts, and an autouse fixture
makes any socket connection fail.

Expected behaviour, written from the spec before the code was opened:
- B2-1: `meta_from_info(info, url)` / `fetch_metadata(url, ydl_factory=…)` read the duration,
  whether there is audio, the chapters and the spoken language (the video's, else its audio
  track's) without downloading; a playlist, a live or an upcoming stream is refused (`MediaError`),
  and a yt-dlp failure becomes `MediaError` keeping yt-dlp's reason.
- B2-2: `suggest_entry(meta, case_id)` follows the README's heuristics: a Japanese title with 解説
  → `ja`, narrated; English, 2 h → `full`; 20 min "highlights" → `edited`; no audio → `language:
  none`, not narrated; `unsure` lists what it can't tell, `title` is always unsure, and the other
  language's title half starts with 【要翻訳】 / "[to translate] ". Fixed values: `source: youtube`,
  `source_url` (without `&list=`), `synthetic_speech: false`, `default_step_track: ai`,
  `data_note: null`. The suggestion plus its duration passes B4's `build_case` once the title is
  translated.
- B2-3: `download(url, out_dir, ydl_factory=…)` moves the finished file into place as
  `out_dir/source.mp4`; a yt-dlp failure gives `MediaError`, leaves no partial file and keeps an
  earlier `source.*`.
- B2-4: `scrubgpt-brain youtube <url> --case-id <id>` prints the YAML suggestion (a one-entry list
  under comment lines) on stdout and exits 0; an error exits 1 with `scrubgpt-brain: error: …` on
  stderr. The CLI is run in-process (`cli.main`) with the stub, since a child process would reach
  the network; only a usage error, which stops before yt-dlp, runs as a child.
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest
import yaml
from scrubgpt_brain import cli as brain_cli
from scrubgpt_brain.engines.media import MediaError
from scrubgpt_brain.pipeline import cases, youtube

URL = "https://www.youtube.com/watch?v=T1synth0001"
PAGE = "https://www.youtube.com/watch?v=T1synth0001"
JA_MARK, EN_MARK = "【要翻訳】", "[to translate] "


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """No network, ever: any socket connection fails, and the real yt-dlp factory is replaced by
    one that fails, so only a test's own stub can answer."""

    def refuse(*args, **kwargs):
        raise AssertionError("a B2 test tried to use the network")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(youtube, "youtube_dl", lambda options: (_ for _ in ()).throw(
        AssertionError("the real yt-dlp was called")
    ))  # fmt: skip


def info(**overrides) -> dict:
    """A synthetic yt-dlp info dict for one finished video (the shape of `extract_info(url,
    download=False)` / `yt-dlp --dump-json`)."""
    base = {
        "id": "T1synth0001",
        "title": "Robot-assisted radical prostatectomy",
        "webpage_url": PAGE,
        "duration": 7200,
        "channel": "T1 Synthetic Channel",
        "upload_date": "20260102",
        "description": "A full-length case.",
        "license": "Standard YouTube License",
        "live_status": "not_live",
        "formats": [
            {"format_id": "137", "vcodec": "avc1.640028", "acodec": "none", "height": 1080},
            {"format_id": "140", "vcodec": "none", "acodec": "mp4a.40.2", "language": "en"},
        ],
        "chapters": [
            {"start_time": 0.0, "end_time": 600.0, "title": "Ports"},
            {"start_time": 600.0, "end_time": 7200.0, "title": "Prostatectomy"},
        ],
    }
    base.update(overrides)
    return base


class StubYDL:
    """A `yt_dlp.YoutubeDL` stand-in: returns a saved info dict and, when asked to download,
    writes a file where yt-dlp's `paths`/`outtmpl` options say (or fails like yt-dlp)."""

    calls: list[tuple[str, bool]]

    def __init__(self, options, *, info_dict=None, fail_extract=None, fail_download=None,
                 content=b"T1 synthetic video bytes", ext="mp4") -> None:  # fmt: skip
        self.options = options
        self.info_dict = info_dict if info_dict is not None else info()
        self.fail_extract = fail_extract
        self.fail_download = fail_download
        self.content = content
        self.ext = ext
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def extract_info(self, url, download=True):
        self.calls.append(("extract_info", download))
        if download:
            raise AssertionError("B2 must read metadata without downloading")
        if self.fail_extract:
            raise self.fail_extract
        return self.info_dict

    def process_ie_result(self, ie_result, download=True):
        self.calls.append(("process_ie_result", download))
        paths = self.options.get("paths") or {}
        home = Path(paths.get("home", "."))
        temp = Path(paths.get("temp", home))
        template = self.options.get("outtmpl", {})
        template = template.get("default") if isinstance(template, dict) else template
        name = (template or "%(title)s.%(ext)s") % {"ext": self.ext, "id": ie_result["id"],
                                                     "title": ie_result["title"]}  # fmt: skip
        temp.mkdir(parents=True, exist_ok=True)
        part = temp / f"{Path(name).stem}.f137.{self.ext}.part"
        part.write_bytes(self.content[:5])
        if self.fail_download:
            raise self.fail_download
        part.unlink()
        home.mkdir(parents=True, exist_ok=True)
        (home / name).write_bytes(self.content)
        return ie_result


def factory(made: list | None = None, **kwargs):
    def make(options):
        ydl = StubYDL(options, **kwargs)
        if made is not None:
            made.append(ydl)
        return ydl

    return make


def meta(**overrides):
    return youtube.meta_from_info(info(**overrides), URL)


# ── B2-1 ─────────────────────────────────────────────────────────────────────


def test_b2_1_metadata_is_read_from_an_info_dict():
    """B2-1 "Metadata is read from an info dict: duration, audio, chapters, language" (README:
    "the video's duration, audio, yt-dlp language and chapters, its channel, upload date and
    licence")."""
    m = meta()
    assert m.duration_s == 7200.0
    assert m.has_audio is True
    assert [tuple(c) for c in m.chapters] == [(0.0, "Ports"), (600.0, "Prostatectomy")]
    assert m.language == "en"
    assert m.url == PAGE and m.video_id == "T1synth0001"
    assert m.title == "Robot-assisted radical prostatectomy"
    assert m.channel == "T1 Synthetic Channel"
    assert m.upload_date == "2026-01-02"


def test_b2_1_the_videos_language_wins_over_its_audio_tracks():
    """README "`language`: yt-dlp's spoken language (the video's, else its audio track's)": the
    info dict's `language` is used when there is one; else the audio format's."""
    assert meta(language="ja").language == "ja"
    formats = [
        {"format_id": "1", "vcodec": "avc1", "acodec": "none"},
        {"format_id": "2", "vcodec": "none", "acodec": "opus", "language": "ja"},
    ]
    assert meta(formats=formats).language == "ja"


def test_b2_1_no_audio_format_means_no_audio():
    """B2-1 "… audio": a video whose formats all have `acodec: none` has no audio."""
    formats = [{"format_id": "137", "vcodec": "avc1.640028", "acodec": "none"}]
    m = meta(formats=formats)
    assert m.has_audio is False
    assert m.language is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"_type": "playlist", "entries": []},
        {"_type": "multi_video", "entries": []},
        {"live_status": "is_live"},
        {"live_status": "is_upcoming"},
    ],
    ids=["playlist", "multi-video", "live", "upcoming"],
)
def test_b2_1_playlists_and_live_or_upcoming_streams_are_refused(overrides):
    """B2-1 "Playlists and live or upcoming streams are refused" (README Errors: "a playlist, a
    channel, or a live or upcoming stream"): `MediaError`, from the info dict and through
    `fetch_metadata`."""
    with pytest.raises(MediaError):
        youtube.meta_from_info(info(**overrides), URL)
    with pytest.raises(MediaError):
        youtube.fetch_metadata(URL, ydl_factory=factory(info_dict=info(**overrides)))


def test_b2_1_fetch_metadata_reads_without_downloading():
    """README "It reads one YouTube video's metadata with yt-dlp, without downloading it": the
    stub is asked once, with `download=False`, and gives the same metadata as the info dict."""
    made: list[StubYDL] = []
    m = youtube.fetch_metadata(URL, ydl_factory=factory(made))
    assert m == meta()
    assert [ydl.calls for ydl in made] == [[("extract_info", False)]]


def test_b2_1_a_yt_dlp_failure_keeps_its_reason():
    """README "any yt-dlp failure (network, a removed or private video, an age gate)" exits 1
    "keeping yt-dlp's reason": `fetch_metadata` raises `MediaError` with yt-dlp's message."""
    failure = RuntimeError(
        "ERROR: [youtube] T1synth0001: Private video. Sign in if you've been granted access"
    )  # noqa: E501
    with pytest.raises(MediaError) as caught:
        youtube.fetch_metadata(URL, ydl_factory=factory(fail_extract=failure))
    assert "Private video" in str(caught.value)


# ── B2-2 ─────────────────────────────────────────────────────────────────────


def _suggest(case_id="yt-en-01", **overrides):
    return youtube.suggest_entry(meta(**overrides), case_id)


def test_b2_2_the_entry_has_every_registry_field_and_the_fixed_values():
    """README "Fixed values: `source: youtube`, `source_url` (the video page, without `&list=`),
    `synthetic_speech: false`, `default_step_track: ai`, and `data_note: null`", with every
    registry field (B4's), in that order, and the case id given. The URL given is a watch URL
    inside a playlist; yt-dlp's info dict names the video's own page (`webpage_url`)."""
    listed = PAGE + "&list=PLt1synthetic&index=3"
    entry, unsure = youtube.suggest_entry(youtube.meta_from_info(info(), listed), "yt-en-01")
    assert list(entry) == list(cases.REGISTRY_FIELDS)
    assert entry["id"] == "yt-en-01"
    assert entry["source"] == "youtube"
    assert entry["source_url"] == PAGE
    assert entry["synthetic_speech"] is False
    assert entry["default_step_track"] == "ai"
    assert entry["data_note"] is None
    assert set(unsure) <= set(cases.REGISTRY_FIELDS)


def test_b2_2_a_japanese_title_with_kaisetsu_is_ja_and_narrated():
    """B2-2 "a Japanese title with 解説 → `ja`, narrated true" (README: kana or kanji → `ja`;
    narration wording such as 解説 → narrated). Here yt-dlp reports no language, so `language` is
    a guess and unsure; narrated isn't."""
    entry, unsure = _suggest(
        "yt-ja-01", title="ロボット支援前立腺全摘除術 手術動画 解説", language=None,
        formats=[{"format_id": "18", "vcodec": "avc1", "acodec": "mp4a.40.2"}],
    )  # fmt: skip
    assert entry["language"] == "ja"
    assert entry["narrated"] is True
    assert "language" in unsure and "narrated" not in unsure
    assert entry["title"]["ja"] == "ロボット支援前立腺全摘除術 手術動画 解説"
    assert entry["title"]["en"] == EN_MARK + entry["title"]["ja"]


def test_b2_2_english_two_hours_is_full():
    """B2-2 "English, 2 h → `full`" (README: `full` unless shorter than 45 min or cut down;
    unsure only under 90 min or with no duration): sure about `video_type` and `language`."""
    entry, unsure = _suggest(duration=7200, language="en-US")
    assert entry["language"] == "en" and "language" not in unsure
    assert entry["video_type"] == "full" and "video_type" not in unsure
    assert entry["title"]["en"] == "Robot-assisted radical prostatectomy"
    assert entry["title"]["ja"] == JA_MARK + "Robot-assisted radical prostatectomy"


def test_b2_2_twenty_minute_highlights_are_edited():
    """B2-2 "20 min "highlights" → `edited`" (README: shorter than 45 min, or "highlights")."""
    entry, _ = _suggest(duration=1200, title="RARP highlights: difficult apex")
    assert entry["video_type"] == "edited"


@pytest.mark.parametrize(
    ("duration", "title", "video_type", "unsure_type"),
    [
        (7200, "RARP highlights", "edited", False),  # long, but the text says cut down
        (7200, "RARP unedited full case", "full", False),  # "unedited" doesn't count
        (1800, "RARP full case", "edited", False),  # under 45 min
        (3600, "RARP full case", "full", True),  # 45-90 min: full, unsure
        (None, "RARP full case", "full", True),  # duration unknown
        (7200, "前立腺全摘 ダイジェスト", "edited", False),  # Japanese "digest"
    ],
)
def test_b2_2_video_type_follows_the_documented_rules(duration, title, video_type, unsure_type):
    """README "`video_type`: `edited` if the video is shorter than 45 min …, or if the text says
    it was cut down (… "highlights", …, ダイジェスト, …; "unedited" doesn't count). Otherwise
    `full`, unsure when the video is under 90 min or its duration is unknown"."""
    entry, unsure = _suggest(duration=duration, title=title)
    assert entry["video_type"] == video_type
    assert ("video_type" in unsure) is unsure_type, unsure


def test_b2_2_no_audio_gives_language_none_and_not_narrated():
    """B2-2 "no audio → `language: none`, narrated false" (README "No audio track → `none`"),
    even with narration wording in the text; the result passes B4 (D-049: `none` ⇒ no
    narration)."""
    entry, unsure = _suggest(
        title="RARP narrated by the surgeon",
        formats=[{"format_id": "137", "vcodec": "avc1", "acodec": "none"}],
    )
    assert entry["language"] == "none"
    assert entry["narrated"] is False
    assert "title" in unsure


@pytest.mark.parametrize(
    ("overrides", "language", "narrated", "unsure_fields"),
    [
        ({"language": "en", "description": "Full case with commentary."}, "en", True, set()),
        ({"language": "en", "description": "Full case."}, "en", False, {"narrated"}),
        ({"language": "de", "title": "RARP Fall"}, "en", False, {"language", "narrated"}),
        ({"language": "ja", "title": "前立腺 ナレーション付き"}, "ja", True, set()),
    ],
    ids=["en-commentary", "en-silent-text", "other-language", "ja-narration"],
)
def test_b2_2_language_and_narrated_follow_the_documented_rules(
    overrides, language, narrated, unsure_fields
):
    """README "`language`: yt-dlp's spoken language … if it is `ja` or `en`. Otherwise it
    guesses, marked unsure" and "`narrated`: true when there is audio, a `ja`/`en` language, and
    narration wording … Otherwise false, and unsure"."""
    entry, unsure = _suggest(**overrides)
    assert entry["language"] == language
    assert entry["narrated"] is narrated
    for name in ("language", "narrated"):
        assert (name in unsure) is (name in unsure_fields), (name, unsure)


@pytest.mark.parametrize("title", ["RARP full case", "ロボット支援前立腺全摘除術"])
def test_b2_2_title_is_always_unsure_with_the_translate_marker(title):
    """B2-2 "`title` is always unsure, with the documented translate marker" (README: "the
    original title in both halves. The other language's half starts with `【要翻訳】` or
    `[to translate] `")."""
    entry, unsure = _suggest(title=title)
    assert "title" in unsure
    japanese = title != "RARP full case"
    original, other, mark = ("ja", "en", EN_MARK) if japanese else ("en", "ja", JA_MARK)
    assert entry["title"][original] == title
    assert entry["title"][other] == mark + title


@pytest.mark.parametrize(
    "overrides",
    [
        {"title": "ロボット支援前立腺全摘除術 解説", "language": "ja", "duration": 1500},
        {"duration": 7200},
        {"formats": [{"format_id": "137", "vcodec": "avc1", "acodec": "none"}], "duration": 900},
    ],
    ids=["ja-narrated-edited", "en-full", "no-audio"],
)
def test_b2_2_a_translated_suggestion_passes_b4(overrides):
    """B2-2 "A suggestion plus its duration passes B4's `build_case` once a person has translated
    the title" (README: "B4 then validates the entry against the contract"): the marked half is
    replaced by a translation and B4 builds a valid partial `Case` with the default YouTube
    note."""
    m = meta(**overrides)
    entry, _ = youtube.suggest_entry(m, "yt-ja-07")
    for lang, mark in (("ja", JA_MARK), ("en", EN_MARK)):
        if entry["title"][lang].startswith(mark):
            entry["title"][lang] = f"T1 translation ({lang})"
    case = cases.build_case(entry, m.duration_s)
    assert case.status.value == "partial"
    assert case.data_note.en == cases.DEFAULT_DATA_NOTES["youtube"]["en"]
    assert case.duration_s == m.duration_s


@pytest.mark.parametrize("case_id", ["YT-JA-01", "yt_ja_01", "", "yt-ja-01-"])
def test_b2_2_an_invalid_case_id_is_refused(case_id):
    """README Errors: "an invalid case id" (plan §4.1 case ids such as `yt-ja-02`)."""
    with pytest.raises(ValueError):
        youtube.suggest_entry(meta(), case_id)


def test_b2_2_the_suggestion_yaml_is_a_one_entry_list_under_comments():
    """README "prints a **suggested registry entry** for B4 as YAML: a one-entry list, ready to
    paste into the registry. Comments above the entry give the video's duration, audio, yt-dlp
    language and chapters, its channel, upload date and licence, and the fields the importer is
    `unsure` of"."""
    m = meta()
    entry, unsure = youtube.suggest_entry(m, "yt-en-01")
    text = youtube.suggestion_yaml(m, entry, unsure)
    assert yaml.safe_load(text) == [entry]
    head = text.split("\n- ", 1)[0] if not text.startswith("- ") else ""
    comments = [line for line in head.splitlines() if line.strip()]
    assert comments and all(line.startswith("#") for line in comments), head
    joined = "\n".join(comments)
    # "chapters": the README doesn't say titles or a count; the two chapters must show either way.
    assert "Ports" in joined or "2 chapter" in joined, joined
    assert any(d in joined for d in ("2:00:00", "120 min", "7200", "2 h")), joined  # duration
    assert "audio" in joined and " en" in joined, joined  # audio, yt-dlp language
    for fact in ("T1 Synthetic Channel", "2026-01-02", "Standard YouTube License"):
        assert fact in joined, fact
    for name in unsure:
        assert name in joined, name


# ── B2-3 (download; FFmpeg must be installed for the merge, README) ─────────


def test_b2_3_download_moves_the_file_into_place(media, tmp_path):
    """B2-3 "`download` moves the file into place" (README: "saves the video as
    `<out_dir>/source.mp4`"): the stub's finished file ends up as `source.mp4`, nothing else is
    left in the folder, and the metadata was checked before the download."""
    made: list[StubYDL] = []
    path = youtube.download(URL, tmp_path / "src", ydl_factory=factory(made))
    assert path == tmp_path / "src" / "source.mp4"
    assert path.read_bytes() == b"T1 synthetic video bytes"
    assert sorted(p.name for p in (tmp_path / "src").iterdir()) == ["source.mp4"]
    assert made[0].calls == [("extract_info", False), ("process_ie_result", True)]


def test_b2_3_a_new_download_replaces_an_earlier_source(media, tmp_path):
    """README "it also saves the video as `<out_dir>/source.mp4`": a later download over an
    earlier `source.mp4` leaves the new file, and other files in the folder alone."""
    out = tmp_path / "src"
    out.mkdir()
    (out / "source.mp4").write_bytes(b"old")
    (out / "notes.txt").write_text("keep", encoding="utf-8")
    youtube.download(URL, out, ydl_factory=factory(content=b"new video"))
    assert (out / "source.mp4").read_bytes() == b"new video"
    assert sorted(p.name for p in out.iterdir()) == ["notes.txt", "source.mp4"]


@pytest.mark.parametrize("earlier", [None, "source.mp4", "source.webm"])
def test_b2_3_a_failed_download_leaves_nothing_and_keeps_the_earlier_source(
    media, tmp_path, earlier
):
    """B2-3 "A yt-dlp failure gives `MediaError` with no partial file left, and an earlier
    `source.*` is kept" (README: "A failed download leaves no `source.*` behind and keeps an
    earlier one"): the stub writes a `.part` file and then fails like yt-dlp."""
    out = tmp_path / "src"
    out.mkdir()
    before = {}
    if earlier:
        (out / earlier).write_bytes(b"earlier download")
        before = {earlier: b"earlier download"}
    failure = RuntimeError("ERROR: unable to download video data: HTTP Error 403: Forbidden")
    with pytest.raises(MediaError) as caught:
        youtube.download(URL, out, ydl_factory=factory(fail_download=failure))
    assert "403" in str(caught.value)
    after = {p.relative_to(out).as_posix(): p.read_bytes() for p in out.rglob("*") if p.is_file()}
    assert after == before, after
    assert [p.name for p in out.iterdir() if p.is_dir()] == []


def test_b2_3_a_playlist_is_refused_before_downloading(media, tmp_path):
    """B2-1/B2-3: a playlist URL is refused (`MediaError`) before anything is downloaded, and
    leaves nothing behind."""
    made: list[StubYDL] = []
    with pytest.raises(MediaError):
        youtube.download(URL, tmp_path / "src", ydl_factory=factory(made, info_dict=info(
            _type="playlist", entries=[]
        )))  # fmt: skip
    assert all(call[0] != "process_ie_result" for ydl in made for call in ydl.calls)
    assert not [p for p in (tmp_path / "src").rglob("*") if p.is_file()]


# ── B2-4 (CLI, in-process with the stub) ─────────────────────────────────────


def _cli(monkeypatch, capsys, argv, **stub):
    monkeypatch.setattr(youtube, "youtube_dl", factory(**stub))
    code = brain_cli.main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_b2_4_the_cli_prints_the_yaml_suggestion_and_exits_0(monkeypatch, capsys):
    """B2-4 "The CLI prints the YAML suggestion and exits 0" (README usage `scrubgpt-brain
    youtube <url> --case-id yt-ja-01`): stdout is the YAML (its one entry is `suggest_entry`'s)
    and stderr is empty."""
    code, out, err = _cli(monkeypatch, capsys, ["youtube", URL, "--case-id", "yt-en-04"])
    assert code == 0, err
    assert not err.strip(), err
    entry, _ = youtube.suggest_entry(meta(), "yt-en-04")
    assert yaml.safe_load(out) == [entry]


@pytest.mark.parametrize(
    ("argv_case", "stub", "needle"),
    [
        ("yt-en-04", {"fail_extract": RuntimeError("ERROR: Video unavailable")}, "unavailable"),
        ("yt-en-04", {"info_dict": info(_type="playlist", entries=[])}, "playlist"),
        ("yt-en-04", {"info_dict": info(live_status="is_upcoming")}, "upcoming"),
        ("Not_A_Case", {}, "Not_A_Case"),
    ],
    ids=["yt-dlp-failure", "playlist", "upcoming", "invalid-case-id"],
)  # fmt: skip
def test_b2_4_an_error_exits_1_with_the_message_on_stderr(
    monkeypatch, capsys, argv_case, stub, needle
):
    """B2-4 "an error exits 1, with the message on stderr" (README Errors: "exit 1 with
    `scrubgpt-brain: error: …`, keeping yt-dlp's reason"): nothing on stdout."""
    code, out, err = _cli(monkeypatch, capsys, ["youtube", URL, "--case-id", argv_case], **stub)
    assert code == 1, (code, out, err)
    assert err.startswith("scrubgpt-brain: error:") and needle in err, err
    assert not out.strip(), out


def test_b2_4_the_cli_download_option_saves_source_mp4(media, monkeypatch, capsys, tmp_path):
    """README "With `--download`, it also saves the video as `<out_dir>/source.mp4`": the YAML
    still goes to stdout, the file is in place, exit 0."""
    out_dir = tmp_path / "dl"
    code, out, err = _cli(
        monkeypatch, capsys, ["youtube", URL, "--case-id", "yt-en-05", "--download", str(out_dir)]
    )
    assert code == 0, err
    assert (out_dir / "source.mp4").read_bytes() == b"T1 synthetic video bytes"
    assert yaml.safe_load(out)[0]["id"] == "yt-en-05"


def test_b2_4_a_missing_case_id_is_a_usage_error(cli):
    """CLI docstring "2 = usage error": `youtube <url>` without `--case-id` exits 2 before any
    yt-dlp call (a child process: argparse stops first, so no network is reached)."""
    result = cli.run("youtube", URL)
    assert result.returncode == 2, (result.returncode, result.stdout, result.stderr)
    assert "--case-id" in result.stderr
    assert not result.stdout.strip()
