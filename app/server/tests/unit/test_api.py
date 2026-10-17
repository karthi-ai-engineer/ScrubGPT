"""The app server's HTTP API (I1): cases, references, media with Range, errors as ApiError."""

from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from scrubgpt_app.api import create_app
from scrubgpt_app.settings import REPO_ROOT, Settings
from scrubgpt_contracts.models.common import ApiError

FIXTURES = REPO_ROOT / "contracts" / "fixtures"
CASE_ID = "case-fixture-01"
FIXTURE_CASE = FIXTURES / "cases" / CASE_ID

VIDEO = f"/media/cases/{CASE_ID}/video.mp4"


def settings_for(data_dir: Path, web_dist: Path) -> Settings:
    return replace(Settings.load({"DATA_DIR": str(data_dir)}, dotenv=False), web_dist=web_dist)


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app(settings_for(FIXTURES, web_dist=Path("/nonexistent"))))


def assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert ApiError.model_validate(response.json()).error.code.value == code


def test_health(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body == {
        "status": "ok",
        "contract_version": "1.0",
        "brain_mode": "mock",
        "cases": {"loaded": 1, "rejected": 0},
    }


def test_case_list(client: TestClient) -> None:
    (item,) = client.get("/api/cases").json()["cases"]
    assert item["case"]["id"] == CASE_ID
    assert item["case"]["title"]["ja"] and item["case"]["title"]["en"]
    assert item["media"] == {"video": VIDEO, "poster": f"/media/cases/{CASE_ID}/poster.jpg"}
    assert item["counts"]["moments"] > 0
    assert "simulated" in item["trust_labels"]
    assert item["has_metrics"] is True


def test_case_detail_passes_the_documents_through(client: TestClient) -> None:
    body = client.get(f"/api/cases/{CASE_ID}").json()
    assert body["case"]["id"] == CASE_ID
    assert {"timeline", "moments", "questions", "seed_records", "metrics"} <= set(body)
    utterances = body["timeline"]["utterances"]
    assert utterances and all("class" in u and "class_" not in u for u in utterances)
    assert body["seed_records"]["records"][0]["question_id"]


def test_unknown_case_is_404(client: TestClient) -> None:
    assert_error(client.get("/api/cases/case-nope"), 404, "not_found")
    assert_error(client.get("/media/cases/case-nope/video.mp4"), 404, "not_found")


def test_reference(client: TestClient) -> None:
    assert client.get("/api/references/rarp").json()["id"] == "rarp"
    assert_error(client.get("/api/references/nope"), 404, "not_found")


def test_catalog_report(client: TestClient) -> None:
    body = client.get("/api/catalog").json()
    assert body["loaded"] == [{"case_id": CASE_ID, "warnings": []}]
    assert body["rejected"] == [] and body["references"] == ["rarp"]


def test_video_is_served_whole_and_by_range(client: TestClient) -> None:
    whole = client.get(VIDEO)
    assert whole.status_code == 200
    assert whole.headers["content-type"] == "video/mp4"
    assert whole.headers["accept-ranges"] == "bytes"
    size = (FIXTURE_CASE / "video.mp4").stat().st_size
    assert len(whole.content) == size
    part = client.get(VIDEO, headers={"Range": "bytes=100-199"})
    assert part.status_code == 206
    assert part.headers["content-range"] == f"bytes 100-199/{size}"
    assert part.content == whole.content[100:200]


def test_clip_and_poster(client: TestClient) -> None:
    clip = client.get(f"/media/cases/{CASE_ID}/clips/{CASE_ID}.m01.mp4")
    assert clip.status_code == 200 and clip.headers["content-type"] == "video/mp4"
    poster = client.get(f"/media/cases/{CASE_ID}/poster.jpg")
    assert poster.status_code == 200 and poster.headers["content-type"] == "image/jpeg"


@pytest.mark.parametrize(
    "name",
    [
        "case.json",  # package JSON goes through /api, not /media
        "seed_records.json",
        "clips/missing.mp4",
        "..%2F..%2Freference%2Frarp.json",
        "clips/..%2F..%2F..%2Freference%2Frarp.json",
        "clips/sub/deeper.mp4",
    ],
)
def test_only_media_files_of_the_case_are_served(client: TestClient, name: str) -> None:
    assert_error(client.get(f"/media/cases/{CASE_ID}/{name}"), 404, "not_found")


def test_unknown_path_is_an_api_error(client: TestClient) -> None:
    assert_error(client.get("/api/nothing"), 404, "not_found")


def test_built_web_app_is_served(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>app</title>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    web = TestClient(create_app(settings_for(FIXTURES, web_dist=dist)))
    assert "<title>app</title>" in web.get("/").text
    assert "<title>app</title>" in web.get(f"/cases/{CASE_ID}").text  # single-page routes
    assert web.get("/assets/app.js").text == "console.log(1)"
    assert_error(web.get("/api/nothing"), 404, "not_found")
    assert web.get("/api/health").json()["status"] == "ok"
