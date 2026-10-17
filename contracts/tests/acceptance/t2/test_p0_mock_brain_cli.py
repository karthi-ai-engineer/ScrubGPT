"""T2 acceptance: the fake Brain as a process, `scrubgpt-validate live` and `response`
(issue #5 criteria 7, 8, 10).

Sources: issue #5 Team Lead triage; plan §4.5 (console scripts, CI runs the fake Brain and the
live validation), D-025, D-037 (`/health` reports mode: mock).
"""

from __future__ import annotations

import json
import subprocess

import httpx
import pytest

POST_ENDPOINTS = ("transcribe", "extract", "translate", "embed", "ask", "briefing")
ALL_ENDPOINTS = ("health", *POST_ENDPOINTS)


def test_c07_mock_brain_starts_and_health_reports_mock(mock_brain_url, endpoints):
    """#5 c7: `uv run scrubgpt-mock-brain --port <port>` starts and GET /health returns 200 with
    mode: "mock" and contract_version (D-037). Started on a free port, not 8101 (the brief)."""
    r = httpx.get(f"{mock_brain_url}/health", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "mock"
    assert body["contract_version"] == "1.0"
    endpoints["health"].response.model_validate(body)


def test_c07_health_fields_follow_brain_api_md(client):
    """brain_api.md /health (fake Brain row): status ok, mode mock, every tier -> "mock",
    cache_mode off; plan §4.4 "status, model tiers, cache mode"."""
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["cache_mode"] == "off"
    tiers = body["model_tiers"]
    expected = {"VISION_FAST", "VISION_DEEP", "TEXT_SMART", "TEXT_FAST", "STT", "STT_DIARIZE"}
    expected |= {"TTS", "EMBED"}
    assert set(tiers) == expected
    assert all(v == "mock" for v in tiers.values())


def test_c08_validate_live_passes_against_the_fake_brain(mock_brain_url, console_script):
    """#5 c8: `uv run scrubgpt-validate live --base-url <fake Brain>` exits 0 and prints PASS,
    with every endpoint and every (empty request) probe listed as checked."""
    done = subprocess.run(
        [str(console_script("scrubgpt-validate")), "live", "--base-url", mock_brain_url],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    out = done.stdout + done.stderr
    assert done.returncode == 0, out
    assert "PASS" in out
    checked = [line.strip() for line in out.splitlines() if line.strip().startswith("checked")]
    for name in ALL_ENDPOINTS:
        assert any(line.startswith(f"checked {name} ") and "/" in line for line in checked), (
            name,
            out,
        )
    for name in POST_ENDPOINTS:
        assert f"checked {name} (empty request)" in checked, (name, out)
    assert "checked health (empty request)" not in checked


def _call(client, endpoints, request_fixture, audio_fixture, name):
    ep = endpoints[name]
    if name == "health":
        return client.get(ep.path)
    body = request_fixture(name)
    if name == "transcribe":
        files = {"audio": (audio_fixture.name, audio_fixture.read_bytes(), "audio/webm")}
        return client.post(ep.path, data=body, files=files)
    return client.post(ep.path, json=body)


@pytest.mark.parametrize("name", ALL_ENDPOINTS)
def test_c10_validate_response_passes_on_saved_bodies(
    client, endpoints, request_fixture, audio_fixture, tmp_path, name
):
    """#5 c10: `scrubgpt-validate response <name> <file>` passes on a body saved from the fake
    Brain for each endpoint."""
    from scrubgpt_contracts.validate import main as validate_main

    r = _call(client, endpoints, request_fixture, audio_fixture, name)
    assert r.status_code == 200, r.text[:500]
    saved = tmp_path / f"{name}.response.json"
    saved.write_bytes(r.content)
    lines: list[str] = []
    code = validate_main(["response", name, str(saved)], out=lines.append)
    assert code == 0, "\n".join(lines)
    assert any("PASS" in line for line in lines), lines


def test_c10_validate_response_console_script(
    client, endpoints, request_fixture, audio_fixture, tmp_path, console_script
):
    """#5 c10, through the real console script for one endpoint (extract, the richest body)."""
    r = _call(client, endpoints, request_fixture, audio_fixture, "extract")
    saved = tmp_path / "extract.response.json"
    saved.write_text(json.dumps(r.json(), ensure_ascii=False), encoding="utf-8")
    done = subprocess.run(
        [str(console_script("scrubgpt-validate")), "response", "extract", str(saved)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert "PASS" in done.stdout
