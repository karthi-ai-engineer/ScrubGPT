"""I1 acceptance: media serving with HTTP Range (brief criterion 4).

Sources: app/server/CLAUDE.md rule 7 ("Serve video and clips with HTTP Range support so the
browser can seek and play at 8–16×"), app/server/README.md (`GET /media/cases/{case_id}/{path}`:
`video.mp4`, `poster.jpg`, `clips/*.mp4|jpg`, `thumbs/*`, with HTTP Range (206); "nothing else in
a case folder"; all errors are ApiError bodies), plan §4.2 (package files), RFC 9110 §14 (Range
requests: 206 + Content-Range, 416 for an unsatisfiable range).
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from scrubgpt_contracts.models.common import ApiError

CASE_ID = "case-fixture-01"
BASE = f"/media/cases/{CASE_ID}"


def _assert_not_found(response) -> None:
    assert response.status_code == 404, (
        response.status_code,
        response.headers,
        response.text[:200],
    )
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    ApiError.model_validate(body)
    assert body["error"]["code"] == "not_found"


def test_video_full_with_accept_ranges(client: TestClient, fixture_case: Path) -> None:
    """Criterion 4: `video.mp4` is served whole, with `Accept-Ranges: bytes` and video/mp4."""
    data = (fixture_case / "video.mp4").read_bytes()
    response = client.get(f"{BASE}/video.mp4")
    assert response.status_code == 200
    assert response.headers.get("accept-ranges") == "bytes"
    assert response.headers["content-type"].startswith("video/mp4")
    assert response.content == data


@pytest.mark.parametrize(
    ("header", "start", "end"),
    [
        ("bytes=0-99", 0, 99),
        ("bytes=1000-1999", 1000, 1999),
        ("bytes=500000-", 500000, None),
        ("bytes=-256", None, None),
    ],
)
def test_video_range_206(
    client: TestClient, fixture_case: Path, header: str, start: int | None, end: int | None
) -> None:
    """Criterion 4: a `Range` request → 206 with exactly the requested bytes and a matching
    `Content-Range: bytes first-last/size` (RFC 9110 §14.4)."""
    data = (fixture_case / "video.mp4").read_bytes()
    size = len(data)
    if start is None:  # suffix range: the last N bytes
        start, end = size - 256, size - 1
    elif end is None:
        end = size - 1
    response = client.get(f"{BASE}/video.mp4", headers={"Range": header})
    assert response.status_code == 206
    assert response.content == data[start : end + 1]
    assert response.headers["content-range"] == f"bytes {start}-{end}/{size}"
    assert int(response.headers["content-length"]) == end - start + 1
    assert response.headers["content-type"].startswith("video/mp4")


def test_range_on_clip(client: TestClient, fixture_case: Path) -> None:
    """Criterion 4 (rule 7): clips support Range too."""
    clip = fixture_case / "clips" / f"{CASE_ID}.m03.mp4"
    data = clip.read_bytes()
    response = client.get(f"{BASE}/clips/{clip.name}", headers={"Range": "bytes=10-19"})
    assert response.status_code == 206
    assert response.content == data[10:20]
    assert response.headers["content-range"] == f"bytes 10-19/{len(data)}"


def test_unsatisfiable_range_416(client: TestClient, fixture_case: Path) -> None:
    """Criterion 4 (RFC 9110 §15.5.17): a range starting past the end → 416 with
    `Content-Range: bytes */size`."""
    size = (fixture_case / "video.mp4").stat().st_size
    response = client.get(f"{BASE}/video.mp4", headers={"Range": f"bytes={size + 10}-"})
    assert response.status_code == 416
    assert response.headers.get("content-range") == f"bytes */{size}"


@pytest.mark.parametrize(
    ("path", "content_type"),
    [
        ("poster.jpg", "image/jpeg"),
        (f"clips/{CASE_ID}.m01.mp4", "video/mp4"),
        (f"clips/{CASE_ID}.m01.jpg", "image/jpeg"),
        (f"clips/{CASE_ID}.m06.mp4", "video/mp4"),
    ],
)
def test_posters_and_clips_content_type(
    client: TestClient, fixture_case: Path, path: str, content_type: str
) -> None:
    """Criterion 4: posters and clips are served with the right content type and bytes."""
    response = client.get(f"{BASE}/{path}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(content_type)
    assert response.content == (fixture_case / path).read_bytes()


def test_summary_media_urls_serve_the_files(client: TestClient, fixture_case: Path) -> None:
    """Criterion 3/4: `media.video` and `media.poster` in the CaseSummary point to these files."""
    media = client.get("/api/cases").json()["cases"][0]["media"]
    video = client.get(media["video"], headers={"Range": "bytes=0-15"})
    assert video.status_code == 206
    assert video.content == (fixture_case / "video.mp4").read_bytes()[:16]
    poster = client.get(media["poster"])
    assert poster.status_code == 200
    assert poster.content == (fixture_case / "poster.jpg").read_bytes()


def test_thumbs_are_served(make_client, data_dir: Path, fixture_case: Path) -> None:
    """Criterion 4 (README): files in `thumbs/` are media and are served."""
    thumbs = data_dir / "cases" / CASE_ID / "thumbs"
    thumbs.mkdir()
    shutil.copy2(fixture_case / "poster.jpg", thumbs / "strip_000.jpg")
    response = make_client(data_dir).get(f"{BASE}/thumbs/strip_000.jpg")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/jpeg")


@pytest.mark.parametrize(
    "path",
    [
        "case.json",
        "timeline.json",
        "moments.json",
        "questions.json",
        "seed_records.json",
        "metrics.json",
        "clips",
        "clips/",
        "",
        "notes.txt",
        "clips/readme.txt",
        "clips/case-fixture-01.m01.json",
        "clips/../case.json",
        "clips/%2e%2e/case.json",
        "clips%2F..%2Fcase.json",
        "%2e%2e/%2e%2e/reference/rarp.json",
        "..%2F..%2Freference%2Frarp.json",
        "..%5C..%5Creference%5Crarp.json",
        "%252e%252e/%252e%252e/reference/rarp.json",
        "%2e%2e%2f%2e%2e%2f%2e%2e%2fpyproject.toml",
        "..%c0%af..%c0%afreference/rarp.json",
        "video.mp4%00.json",
        "/etc/passwd",
        "%2Fetc%2Fpasswd",
        "C:%5CWindows%5Cwin.ini",
        "C:/Windows/win.ini",
    ],
)
def test_only_media_files_are_served(
    make_client, data_dir: Path, fixture_case: Path, path: str
) -> None:
    """Criterion 4: nothing outside a case's media files is served: package JSON, other files,
    other folders and path traversal in any encoding → 404 `ApiError`."""
    case_dir = data_dir / "cases" / CASE_ID
    (case_dir / "notes.txt").write_text("private", encoding="utf-8")
    (case_dir / "clips" / "readme.txt").write_text("private", encoding="utf-8")
    (case_dir / "clips" / f"{CASE_ID}.m01.json").write_text("{}", encoding="utf-8")
    client = make_client(data_dir)
    _assert_not_found(client.get(f"{BASE}/{path}"))


@pytest.mark.parametrize(
    "url",
    [
        "/media/cases/no-such-case/video.mp4",
        "/media/cases/%2e%2e/reference/rarp.json",
        "/media/cases/..%2Freference/rarp.json",
        "/media/cases/%2e%2e%2fcases%2fcase-fixture-01/video.mp4",
        "/media/cases/case-fixture-01",
        "/media/cases/case-fixture-01/",
        "/media/reference/rarp.json",
        "/media/cases/case-fixture-01/subdir/video.mp4",
    ],
)
def test_media_outside_cases_not_found(client: TestClient, url: str) -> None:
    """Criterion 4: unknown cases and paths outside a case folder → 404 `ApiError`."""
    _assert_not_found(client.get(url))


def test_rejected_case_media_not_served(make_client, data_dir: Path, clone_case) -> None:
    """Criterion 4 + CLAUDE.md rule 2: only loaded (valid) packages exist for the server, so a
    rejected package's video is not served either."""
    clone = clone_case(data_dir / "cases", "case-fixture-02")
    (clone / "moments.json").write_text("not json", encoding="utf-8")
    client = make_client(data_dir)
    _assert_not_found(client.get("/media/cases/case-fixture-02/video.mp4"))


def test_no_directory_listing(client: TestClient) -> None:
    """Criterion 4: no listing of a case's folders."""
    for url in (f"{BASE}/clips/", f"{BASE}/thumbs/", "/media/cases/", "/media/"):
        response = client.get(url)
        assert response.status_code == 404
        assert not re.search(r"case-fixture-01\.m0\d\.mp4", response.text)
