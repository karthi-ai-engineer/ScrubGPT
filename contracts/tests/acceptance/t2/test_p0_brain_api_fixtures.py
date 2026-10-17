"""T2 acceptance: the Brain API request fixtures (issue #5 criteria 5, 6).

Sources: issue #5 Team Lead triage; plan §4.4 (audio webm/opus or mp4/aac), §4.5 and D-036
(synthetic media only, <= 5 MB under contracts/fixtures/), D-037 (`<endpoint>.request.json`).
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess

import pytest

POST_ENDPOINTS = ("transcribe", "extract", "translate", "embed", "ask", "briefing")


@pytest.mark.parametrize("name", POST_ENDPOINTS)
def test_c05_request_fixture_exists_and_validates(endpoints, paths, name):
    """#5 c5: contracts/fixtures/brain_api/<name>.request.json exists for each of the 6 POST
    endpoints and validates against that endpoint's request model."""
    path = paths["brain_api"] / f"{name}.request.json"
    assert path.is_file(), path
    body = json.loads(path.read_text(encoding="utf-8"))
    endpoints[name].request.model_validate(body)


def test_c05_no_request_fixture_for_health(paths):
    """#5 c5 / brain_api.md: request fixtures are for the POST endpoints; GET /health has none."""
    assert not (paths["brain_api"] / "health.request.json").exists()


def test_c05_extract_fixture_uses_a_fixture_question(paths, case_data):
    """#5 c5: extract.request.json uses a fixture question id (case-fixture-01.m01.q1, ...); the
    full question and moment travel (plan §4.4), so they are the fixture case's objects."""
    body = json.loads((paths["brain_api"] / "extract.request.json").read_text(encoding="utf-8"))
    qid = body["question"]["id"]
    assert qid.startswith("case-fixture-01.m")
    assert qid in case_data["questions"]
    assert body["question"] == case_data["questions"][qid]
    assert body["moment"] == case_data["moments"][body["question"]["moment_id"]]
    assert body["case_context"]["case"] == case_data["case"]
    assert body["case_context"]["step"] == case_data["steps"][body["moment"]["step_id"]]


def test_c06_exactly_one_audio_fixture_small_and_in_a_4_4_format(paths, audio_fixture):
    """#5 c6: exactly one transcribe.request.audio.<ext> exists; it is in a §4.4 format
    (webm/opus or mp4/aac) and is <= 100 KB."""
    found = sorted(paths["brain_api"].glob("transcribe.request.audio.*"))
    assert found == [audio_fixture]
    assert audio_fixture.stat().st_size <= 100 * 1024
    assert audio_fixture.stat().st_size > 0
    assert audio_fixture.suffix.lower() in (".webm", ".mp4", ".m4a")


def _ffprobe(path):
    exe = shutil.which("ffprobe")
    if exe is None:
        pytest.skip("ffprobe not on PATH (needed to inspect the audio fixture)")
    done = subprocess.run(
        [exe, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return json.loads(done.stdout)


def test_c06_audio_fixture_codec_matches_container(audio_fixture):
    """#5 c6 / plan §4.4: webm/opus or mp4/aac; audio only (no video stream)."""
    info = _ffprobe(audio_fixture)
    streams = info["streams"]
    assert [s["codec_type"] for s in streams] == ["audio"], streams
    codec = streams[0]["codec_name"]
    container = info["format"]["format_name"]
    if audio_fixture.suffix.lower() == ".webm":
        assert "webm" in container or "matroska" in container
        assert codec == "opus"
    else:
        assert "mp4" in container or "m4a" in container
        assert codec == "aac"


def test_c06_audio_fixture_is_a_synthetic_tone(audio_fixture):
    """#5 c6 / D-036: synthetic audio (an FFmpeg tone). Decoded, almost all of its energy sits
    in one narrow frequency band (a pure tone, not speech or surgical audio), and it was muxed
    by FFmpeg (Lavf)."""
    info = _ffprobe(audio_fixture)
    tags = {k.lower(): v for k, v in info["format"].get("tags", {}).items()}
    assert "lavf" in tags.get("encoder", "").lower(), tags
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        pytest.skip("ffmpeg not on PATH")
    rate = 8000
    raw = subprocess.run(
        [ffmpeg, "-v", "error", "-i", str(audio_fixture), "-ac", "1", "-ar", str(rate)]
        + ["-f", "s16le", "-"],
        capture_output=True,
        timeout=60,
        check=True,
    ).stdout
    samples = [int.from_bytes(raw[i : i + 2], "little", signed=True) for i in range(0, len(raw), 2)]
    # skip the codec's start-up transient; use up to 0.5 s
    window = samples[rate // 10 : rate // 10 + rate // 2]
    assert len(window) >= rate // 4, "audio fixture is too short to analyse"
    n = len(window)
    total = sum(x * x for x in window)
    assert total > 0, "audio fixture is silent"

    def band_energy(freq: float) -> float:
        # Goertzel: |X(f)|^2; for a pure tone 2|X|^2 / (n * sum x^2) ~= 1
        w = 2 * math.pi * freq / rate
        coeff = 2 * math.cos(w)
        s1 = s2 = 0.0
        for x in window:
            s0 = x + coeff * s1 - s2
            s2, s1 = s1, s0
        return s1 * s1 + s2 * s2 - coeff * s1 * s2

    freqs = list(range(100, 3000, 20))
    energies = [band_energy(f) for f in freqs]
    peak = max(range(len(freqs)), key=energies.__getitem__)
    # fine search around the peak
    fine = [freqs[peak] + d for d in range(-20, 21, 2)]
    best = max(band_energy(f) for f in fine)
    purity = 2 * best / (n * total)
    assert purity > 0.7, f"not a pure tone: peak ~{freqs[peak]} Hz, purity {purity:.2f}"


def test_c06_fixtures_total_at_most_5_mb(paths):
    """#5 c6 / D-036: contracts/fixtures/ stays <= 5 MB in total."""
    total = sum(p.stat().st_size for p in paths["fixtures"].rglob("*") if p.is_file())
    assert total <= 5 * 1024 * 1024, f"{total} bytes"
