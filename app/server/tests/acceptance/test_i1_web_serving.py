"""I1 acceptance: the server serves the built web app (brief criterion 6).

Sources: app/server/README.md ("When `app/web/dist` exists (`npm run build`), the server also
serves the web app at `/` for the offline demo"), the brief (single-page app: unknown page paths
get the app; `/api/*` and `/media/*` keep their own answers), app/web/CLAUDE.md rule 10 (the demo
works offline).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scrubgpt_contracts.models.common import ApiError

INDEX = (
    "<!doctype html><html><head><title>t2-dist</title></head>"
    "<body><div id=root></div></body></html>"
)


@pytest.fixture
def web_dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX, encoding="utf-8")
    (dist / "assets" / "app-123.js").write_text("console.log('t2');", encoding="utf-8")
    return dist


@pytest.fixture
def web_client(make_client, data_dir: Path, web_dist: Path):
    return make_client(data_dir, web_dist=web_dist)


@pytest.mark.parametrize(
    "path", ["/", "/cases/case-fixture-01", "/cases/unknown", "/some/deep/page"]
)
def test_pages_get_the_web_app(web_client, path: str) -> None:
    """Criterion 6: `/` and unknown page paths get `index.html` (single-page app)."""
    response = web_client.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "t2-dist" in response.text


def test_assets_are_served(web_client) -> None:
    """Criterion 6: the built assets are served."""
    response = web_client.get("/assets/app-123.js")
    assert response.status_code == 200
    assert "t2" in response.text


def test_api_keeps_its_answers(web_client) -> None:
    """Criterion 6: `/api/*` keeps its JSON answers, and unknown API paths stay 404 `ApiError`
    (never the web page)."""
    assert web_client.get("/api/cases").json()["cases"][0]["case"]["id"] == "case-fixture-01"
    for path in ("/api/no-such-endpoint", "/api/cases/unknown", "/api/"):
        response = web_client.get(path)
        assert response.status_code == 404, path
        assert "t2-dist" not in response.text
        ApiError.model_validate(response.json())


def test_media_keeps_its_answers(web_client, fixture_case: Path) -> None:
    """Criterion 6: `/media/*` keeps serving media and its 404 `ApiError`s (never the web page)."""
    response = web_client.get(
        "/media/cases/case-fixture-01/video.mp4", headers={"Range": "bytes=0-9"}
    )
    assert response.status_code == 206
    assert response.content == (fixture_case / "video.mp4").read_bytes()[:10]
    for path in (
        "/media/cases/case-fixture-01/case.json",
        "/media/cases/unknown/video.mp4",
        "/media/other",
    ):
        response = web_client.get(path)
        assert response.status_code == 404, path
        assert "t2-dist" not in response.text
        ApiError.model_validate(response.json())


def test_dist_files_outside_dist_not_served(web_client) -> None:
    """Criterion 6: page paths never reach files outside `dist/` (traversal → the app or 404)."""
    for path in (
        "/%2e%2e/%2e%2e/pyproject.toml",
        "/..%2F..%2Fpyproject.toml",
        "/assets/..%2F..%2Fdata",
    ):
        response = web_client.get(path)
        assert "[project]" not in response.text
        assert "uv_build" not in response.text


def test_without_dist_root_is_not_found(client) -> None:
    """Criterion 6 (converse): without a built app, `/` is a 404 `ApiError`, not a crash."""
    response = client.get("/")
    assert response.status_code == 404
    ApiError.model_validate(response.json())


def test_default_dist_is_app_web_dist(repo_root: Path, make_client, data_dir: Path) -> None:
    """Criterion 6 (README): the web app is served from `app/web/dist` (after `npm run build`).
    Uses the real build when it exists; skipped otherwise."""
    from scrubgpt_app.settings import Settings

    dist = Settings.load({}, dotenv=False).web_dist
    assert dist.resolve() == (repo_root / "app" / "web" / "dist").resolve()
    if not (dist / "index.html").is_file():
        pytest.skip("app/web/dist is not built (run `npm run build` in app/web)")
    client = make_client(data_dir, web_dist=dist)
    for path in ("/", "/cases/case-fixture-01"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.text == (dist / "index.html").read_text(encoding="utf-8")
