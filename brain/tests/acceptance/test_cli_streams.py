"""CLI-1 of the T1 brief at 5a89091: "For every subcommand, results go to stdout and
`scrubgpt-brain: error: …` goes to stderr, with exit codes as documented in the CLI docstring"
(scrubgpt_brain/cli.py; fixes the stream spec gap of Tester 1's #14 report, cd3843e).

Expected behaviour, written from the spec (the CLI docstring) before the code was opened:
- "Results go to stdout, errors to stderr."
- Exit codes: 0 = done; 1 = the input is missing, isn't a video, or FFmpeg failed (for `audio`
  also a video without an audio track or a setting out of range; for `youtube` also a yt-dlp
  failure or an invalid case id; for `reference` also inconsistent knowledge or no data folder);
  2 = usage error.

Each subcommand is run as a child process with a success (stdout has the result, stderr is
empty), an error (exit 1, `scrubgpt-brain: error: …` on stderr, stdout empty) and a usage error
(exit 2, nothing on stdout). `youtube` reaches the network in a child, so only its usage error
runs here; its result and error streams are tested in-process with a stub in
test_b2_youtube.py (B2-4). The FFmpeg commands skip without FFmpeg.
"""

from __future__ import annotations

import pytest
import yaml

ERROR = "scrubgpt-brain: error:"


def assert_result(result) -> None:
    assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
    assert result.stdout.strip(), "no result on stdout"
    assert not result.stderr.strip(), f"stderr on success: {result.stderr}"


def assert_error(result, *needles: str) -> None:
    assert result.returncode == 1, (result.returncode, result.stdout, result.stderr)
    assert result.stderr.startswith(ERROR), f"stderr: {result.stderr!r}"
    assert not result.stdout.strip(), f"stdout on error: {result.stdout}"
    assert "Traceback" not in result.stderr
    for needle in needles:
        assert needle in result.stderr, (needle, result.stderr)


def assert_usage(result) -> None:
    assert result.returncode == 2, (result.returncode, result.stdout, result.stderr)
    assert result.stderr.strip() and not result.stdout.strip(), (result.stdout, result.stderr)


@pytest.fixture(scope="module")
def clip(media, tmp_path_factory):
    """A 6 s synthetic video with a tone, and one without audio (FFmpeg `testsrc2`/`sine`)."""
    folder = tmp_path_factory.mktemp("cli")
    return {
        "video": media.make_video(folder / "clip.mp4", 6.0),
        "silent": media.make_video(folder / "silent.mp4", 6.0, audio=False),
    }


# ── normalize, frames, audio (FFmpeg) ────────────────────────────────────────


@pytest.mark.parametrize("command", ["normalize", "frames", "audio"])
def test_cli1_media_commands_print_results_on_stdout(media, clip, tmp_path, command):
    """CLI-1 "results go to stdout": `normalize`, `frames` and `audio` on a synthetic clip exit 0
    with their result line on stdout and nothing on stderr."""
    assert_result(media.run_cli(command, str(clip["video"]), str(tmp_path / "out")))


@pytest.mark.parametrize("command", ["normalize", "frames", "audio"])
@pytest.mark.parametrize("bad", ["missing", "not-a-video"])
def test_cli1_media_commands_report_a_bad_input_on_stderr(media, tmp_path, command, bad):
    """CLI-1 "`scrubgpt-brain: error: …` goes to stderr" with exit 1 ("the input is missing, isn't
    a video")."""
    source = tmp_path / "input.mp4"
    if bad == "not-a-video":
        source.write_text("not a video\n", encoding="utf-8")
    assert_error(media.run_cli(command, str(source), str(tmp_path / "out")))


def test_cli1_audio_without_an_audio_track_is_exit_1_on_stderr(media, clip, tmp_path):
    """CLI docstring "for `audio` also a video without an audio track": exit 1, the error on
    stderr (README: "… has no audio track")."""
    assert_error(
        media.run_cli("audio", str(clip["silent"]), str(tmp_path / "out")), "no audio track"
    )


@pytest.mark.parametrize("value", ["5", "-1"])
def test_cli1_audio_with_a_setting_out_of_range_is_exit_1_on_stderr(media, clip, tmp_path, value):
    """CLI docstring "for `audio` also … a setting out of range" (README: D1's `max_chunk_s`
    range): exit 1 with the error on stderr, nothing written."""
    out = tmp_path / "out"
    assert_error(media.run_cli("audio", str(clip["video"]), str(out), "--max-chunk", value))
    assert not out.exists() or not any(out.iterdir())


@pytest.mark.parametrize(
    "argv",
    [
        ["normalize"],
        ["frames", "only-one-argument"],
        ["audio", "a", "b", "--max-chunk", "not-a-number"],
        ["frames", "a", "b", "--scene-threshold", "0.3", "--no-scenes"],
    ],
    ids=["normalize-no-args", "frames-one-arg", "audio-bad-number", "frames-exclusive-options"],
)
def test_cli1_media_command_usage_errors_exit_2(cli, argv):
    """CLI docstring "2 = usage error" (argparse): no output on stdout."""
    assert_usage(cli.run(*argv))


# ── reference, case, youtube (no FFmpeg needed for these) ────────────────────


def test_cli1_reference_prints_its_result_on_stdout(cli, tmp_path):
    """CLI-1 for `reference`: exit 0, the result on stdout, nothing on stderr."""
    assert_result(cli.run("reference", str(tmp_path)))


def test_cli1_reference_without_a_data_folder_is_exit_1_on_stderr(cli, tmp_path):
    """CLI docstring "for `reference` also … no data folder": exit 1, error on stderr."""
    assert_error(cli.run("reference", drop_env=("DATA_DIR",), cwd=tmp_path), "DATA_DIR")


def test_cli1_reference_usage_error_exits_2(cli, tmp_path):
    """CLI docstring "2 = usage error": `reference` takes at most one folder."""
    assert_usage(cli.run("reference", str(tmp_path / "a"), str(tmp_path / "b")))


def _registry(tmp_path):
    path = tmp_path / "registry.yaml"
    path.write_text(
        yaml.safe_dump(
            [
                {
                    "id": "synthetic-01", "title": {"ja": "合成症例", "en": "Synthetic case"},
                    "source": "synthetic", "source_url": None, "language": "en",
                    "video_type": "full", "narrated": True, "synthetic_speech": True,
                    "default_step_track": "ai",
                }
            ],
            allow_unicode=True, sort_keys=False,
        ),
        encoding="utf-8",
    )  # fmt: skip
    return path


def test_cli1_case_prints_its_result_on_stdout(media, clip, tmp_path):
    """CLI-1 for `case`: exit 0, the result on stdout, nothing on stderr."""
    result = media.run_cli(
        "case", str(_registry(tmp_path)), "synthetic-01", str(clip["video"]), str(tmp_path / "o")
    )
    assert_result(result)


@pytest.mark.parametrize("bad", ["unknown-case", "missing-registry", "broken-registry"])
def test_cli1_case_errors_are_exit_1_on_stderr(cli, tmp_path, bad):
    """CLI-1 for `case`: an unknown case id (B4-4), a missing registry or one that isn't a YAML
    list exits 1 with the error on stderr, before the video is looked at (none is given)."""
    registry = _registry(tmp_path)
    case_id = "synthetic-01"
    if bad == "unknown-case":
        case_id = "synthetic-99"
    elif bad == "missing-registry":
        registry = tmp_path / "nope.yaml"
    else:
        registry.write_text("just: a mapping\n", encoding="utf-8")
    out = tmp_path / "out"
    assert_error(cli.run("case", str(registry), case_id, str(tmp_path / "no.mp4"), str(out)))
    assert not (out / "case.json").exists()


def test_cli1_case_usage_error_exits_2(cli):
    """CLI docstring "2 = usage error": `case` needs four arguments."""
    assert_usage(cli.run("case", "registry.yaml", "synthetic-01"))


def test_cli1_youtube_usage_error_exits_2(cli):
    """CLI docstring "2 = usage error" for `youtube` (no `--case-id`): it stops before yt-dlp, so
    no network is reached."""
    assert_usage(cli.run("youtube", "https://www.youtube.com/watch?v=T1synth0001"))


def test_cli1_an_unknown_subcommand_is_a_usage_error(cli):
    """CLI docstring "2 = usage error": an unknown command and no command at all."""
    assert_usage(cli.run("transcribe", "x"))
    assert_usage(cli.run())


# ── CLI-1 for the round-3 commands: atlas pick, atlas frames, metrics, ground-truth ──
# Their results on stdout (exit 0, empty stderr) are checked in test_a6_atlas.py,
# test_c7_evaluate.py and test_c8_ground_truth.py; here: errors and usage errors.


@pytest.mark.parametrize(
    "argv",
    [
        ["atlas", "pick", "{tmp}/missing.json", "--out", "{tmp}/index.yaml"],
        ["atlas", "frames", "{tmp}/no-videos", "{tmp}/data", "--index", "{tmp}/missing.yaml"],
        ["metrics", "{tmp}/missing-timeline.json", "{tmp}/out"],
        ["ground-truth", "{tmp}/no-case", "{tmp}/missing.json", "CASE001"],
    ],
    ids=["atlas-pick", "atlas-frames", "metrics", "ground-truth"],
)
def test_cli1_round3_commands_report_a_missing_input_on_stderr(cli, tmp_path, argv):
    """CLI-1 "`scrubgpt-brain: error: …` on stderr with exit 1" for `atlas pick`, `atlas
    frames`, `metrics` and `ground-truth` given a missing input; nothing on stdout, and no output
    file appears."""
    args = [a.replace("{tmp}", str(tmp_path)) for a in argv]
    assert_error(cli.run(*args))
    assert not (tmp_path / "index.yaml").exists() and not (tmp_path / "out").exists()


@pytest.mark.parametrize(
    "argv",
    [
        ["atlas"],
        ["atlas", "pick"],
        ["atlas", "frames"],
        ["atlas", "pick", "f.json", "--per-step", "three"],
        ["atlas", "cut", "f.json"],
        ["metrics", "timeline.json"],
        ["metrics", "timeline.json", "out", "--frame-step", "x"],
        ["ground-truth", "case_dir", "labels.json"],
        ["ground-truth", "case_dir", "labels.json", "CASE001", "--video-fps", "x"],
    ],
    ids=["atlas-no-stage", "pick-no-file", "frames-no-videos", "pick-bad-number",
         "atlas-unknown-stage", "metrics-one-arg", "metrics-bad-step", "gt-two-args",
         "gt-bad-fps"],
)  # fmt: skip
def test_cli1_round3_usage_errors_exit_2(cli, argv):
    """CLI-1 "usage errors exit 2" (CLI docstring "2 = usage error") for the new commands."""
    assert_usage(cli.run(*argv))
