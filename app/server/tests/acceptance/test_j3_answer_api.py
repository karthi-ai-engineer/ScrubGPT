"""J3 answer flow on the app server (brief criteria 5, 7 and the server side of 8).

Sources: plan §2.10 J3, §8.3 (question card → tap / voice / text → (voice) /transcribe →
/extract → read-back chips (an edited chip → /translate) → Confirm → the app server stores the
record + provenance), §4.3 ("If the surgeon edits a chip, the app sends the new text to
/v1/translate"; "The app assigns the UUIDv7 id and fills the confirmation fields"; "trust_label
follows the answerer: operating_surgeon, reviewer, or simulated for role-play"), §4.4 ("Full
objects travel, not IDs: /extract receives the full question, moment and a case_context (the
case.json content plus the moment's step object from the Procedure Reference)"; "The app assigns
one answer_id per answer and sends it with both /transcribe and /extract"); contracts/brain_api.md
(`/extract` request and response, "On Confirm"); D-054, D-056 (`source: edit`, `/v1/translate`
fills the other half, `confirm_draft()` raises while cue or action is null); D-059/D-066 (who may
answer which question); D-071 (UUIDv7 `answer_id`, questions only from `questions.json`, answer
audio stays local); app/server/CLAUDE.md rule 1 ("The app assigns answer_id (UUIDv7) and stores
answer audio locally"); app/server/README.md (API rows for `/api/answers/*`, `/api/translate`,
`/media/answers/…`, `/api/cases/{id}/answer-queue`).
"""

from __future__ import annotations

import copy
from pathlib import Path
from uuid import UUID

import pytest
from scrubgpt_contracts.models.brain_api import ExtractRequest, ExtractResponse
from scrubgpt_contracts.models.case_package import Case, Moment, Question
from scrubgpt_contracts.models.decision_record import DecisionRecord
from uuid6 import uuid7

CASE = "case-fixture-01"
AUDIO = (
    Path(__file__).resolve().parents[4]
    / "contracts"
    / "fixtures"
    / "brain_api"
    / "transcribe.request.audio.webm"
)
EXTRACT = "/v1/answers/extract"


def _question(docs, qid: str) -> dict:
    for q in [*docs["questions"]["operating"], *docs["questions"]["reviewer"]]:
        if q["id"] == qid:
            return q
    raise KeyError(qid)


def _moment(docs, mid: str) -> dict:
    return next(m for m in docs["moments"]["moments"] if m["id"] == mid)


def _step(docs, step_id: str) -> dict:
    for phase in docs["reference"]["phases"]:
        for step in phase["steps"]:
            if step["id"] == step_id:
                return step
    raise KeyError(step_id)


def _same(model, a: dict, b: dict) -> None:
    assert model.model_validate(a).model_dump(mode="json") == model.model_validate(b).model_dump(
        mode="json"
    )


def _is_uuid7(value: str) -> bool:
    try:
        return UUID(value).version == 7
    except (ValueError, TypeError):
        return False


def _confirm(client, body: dict, edits: list[dict], confirmed_by: str = "Dr Test"):
    return client.post(
        "/api/answers/confirm",
        json={
            "answer_id": body["answer_id"],
            "draft": body["extract"]["draft"],
            "edits": edits,
            "confirmed_by": confirmed_by,
        },
    )


def _fill_required(draft: dict, lang: str = "ja") -> list[dict]:
    """Edits for the required fields the draft left null (the surgeon's own words)."""
    edits = []
    if draft["situation_cue"]["text"] is None:
        edits.append({"field": "situation_cue.text", "text": "視野が赤くなった", "lang": lang})
    if draft["action"]["text"] is None:
        edits.append({"field": "action.text", "text": "吸引してから止血した", "lang": lang})
    return edits


# --- criterion 5: answer_id, documented shapes, voice kept locally, role rule -----------------


def test_c5_draft_without_answer_id_gets_a_server_uuid7_used_with_the_brain(
    answer_app, data_dir, draft_for
):
    """Criterion 5 (plan §4.1 "Records and answers: UUIDv7"; README `/api/answers/draft`: "the
    server assigns … answer_id … when absent"): the server assigns a UUIDv7 and sends that same id
    to `/extract`; the draft's answer evidence uses it (brain_api.md)."""
    app = answer_app(data_dir)
    ids = set()
    for _ in range(2):
        status, body = draft_for(app.client, f"{CASE}.m05.q1", text="レンズが曇った")
        assert status == 200, body
        assert _is_uuid7(body["answer_id"])
        ids.add(body["answer_id"])
        sent = app.wire.json_bodies(EXTRACT)[-1]
        assert sent["answer"]["answer_id"] == body["answer_id"]
        ExtractResponse.model_validate(body["extract"])
        evidence_ids = [
            e["answer_id"]
            for e in body["extract"]["draft"]["evidence"]
            if e["kind"] in ("answer_text", "answer_audio")
        ]
        assert evidence_ids and set(evidence_ids) == {body["answer_id"]}
    assert len(ids) == 2, "one answer_id per answer"


def test_c5_a_given_uuid7_answer_id_is_kept(answer_app, data_dir, draft_for):
    """Criterion 5: the id from `/api/answers/audio` is passed to `/api/answers/draft` and kept
    (plan §4.4: the same `answer_id` goes to `/transcribe` and `/extract`)."""
    app = answer_app(data_dir)
    given = str(uuid7())
    status, body = draft_for(app.client, f"{CASE}.m05.q1", answer_id=given)
    assert status == 200, body
    assert body["answer_id"] == given
    assert app.wire.json_bodies(EXTRACT)[-1]["answer"]["answer_id"] == given


@pytest.mark.parametrize("bad", ["not-a-uuid", "01a1436a-d1b8-4311-8fad-49edc656e70d"])
def test_c5_a_non_uuid7_answer_id_is_refused(answer_app, data_dir, draft_for, bad):
    """Criterion 5 (brain_api.md: "UUIDs are UUIDv7"): an answer id that isn't a UUIDv7 never
    becomes an answer's id (400 `bad_request`)."""
    app = answer_app(data_dir)
    status, body = draft_for(app.client, f"{CASE}.m05.q1", answer_id=bad)
    assert status == 400, body
    assert body["error"]["code"] == "bad_request"


@pytest.mark.parametrize(
    ("qid", "role", "mode", "tap", "text", "lang"),
    [
        (
            f"{CASE}.m01.q1",
            "operating_surgeon",
            "tap",
            {"verdict": "confirm", "choice_ids": ["pooling", "view_red"]},
            None,
            "ja",
        ),
        (f"{CASE}.m02.q2", "operating_surgeon", "text", None, "膀胱頸部が見えにくかった", "ja"),
        (f"{CASE}.m04.r1", "reviewer", "text", None, "Because the plane was unclear", "en"),
        (
            f"{CASE}.m03.q1",
            "dev_team_simulated",
            "tap",
            {"verdict": "reject", "choice_ids": []},
            None,
            "en",
        ),
    ],
    ids=["tap", "text_operating", "text_reviewer", "tap_reject_roleplay"],
)
def test_c5_answers_reach_the_brain_with_full_objects(
    answer_app, data_dir, draft_for, fixture_docs, qid, role, mode, tap, text, lang
):
    """Criterion 5 (plan §4.4; brain_api.md `/extract` request): "tap, voice and text answers reach
    the Brain in the documented shapes (full question, moment, case.json, Reference step)"."""
    app = answer_app(data_dir)
    status, body = draft_for(app.client, qid, role, mode=mode, tap=tap, text=text, lang=lang)
    assert status == 200, body
    [sent] = app.wire.json_bodies(EXTRACT)
    ExtractRequest.model_validate(sent)
    question = _question(fixture_docs, qid)
    moment = _moment(fixture_docs, question["moment_id"])
    _same(Question, sent["question"], question)
    _same(Moment, sent["moment"], moment)
    _same(Case, sent["case_context"]["case"], fixture_docs["case"])
    assert sent["case_context"]["step"]["id"] == moment["step_id"]
    reference_step = _step(fixture_docs, moment["step_id"])
    assert sent["case_context"]["step"]["name"] == reference_step["name"]
    assert sent["case_context"]["step"]["checkpoints"] == reference_step["checkpoints"]
    assert sent["answerer_role"] == role
    assert sent["answer"]["mode"] == mode
    assert sent["answer"]["tap"] == tap
    assert sent["answer"]["text"] == text
    assert sent["answer"]["lang"] == lang
    assert sent["answer"]["audio_uri"] is None


def test_c5_voice_is_transcribed_kept_locally_and_served_back(
    answer_app, data_dir, draft_for, repo_root
):
    """Criterion 5 (rule 1: "stores answer audio locally"; README `/api/answers/audio`: "the
    server assigns the UUIDv7 answer_id, keeps the file next to the store (answers/<answer_id>.webm,
    never in Drive or git), transcribes it"; `/media/answers/{answer_id}.webm`; plan §4.4 the same
    answer_id goes to `/transcribe` and `/extract`)."""
    app = answer_app(data_dir)
    audio = AUDIO.read_bytes()
    response = app.client.post(
        "/api/answers/audio",
        files={"audio": ("answer.webm", audio, "audio/webm;codecs=opus")},
        data={"lang_hint": "auto"},
    )
    assert response.status_code == 200, response.text
    heard = response.json()
    answer_id = heard["answer_id"]
    assert _is_uuid7(answer_id)
    assert heard["lang"] == "ja"  # plan §4.5: `auto` → the fake Brain's JA sentence
    assert heard["text"].strip()

    # /transcribe got the audio, the hint and this answer_id.
    [(_, _, headers, sent)] = [c for c in app.wire.calls if c[1] == "/v1/answers/transcribe"]
    assert headers["content-type"].startswith("multipart/form-data")
    assert audio in sent and answer_id.encode() in sent and b"auto" in sent

    # Kept locally under its answer_id, next to the store, and nowhere in the repo or DATA_DIR.
    kept = app.db_path.parent / "answers" / f"{answer_id}.webm"
    assert kept.is_file()
    assert kept.read_bytes() == audio
    assert heard["audio_uri"].endswith(f"{answer_id}.webm")
    assert not [p for p in data_dir.rglob(f"{answer_id}*")]
    assert not [p for p in (repo_root / "app").rglob(f"{answer_id}*")]

    served = app.client.get(f"/media/answers/{answer_id}.webm")
    assert served.status_code == 200
    assert served.content == audio

    # The draft goes out with the same answer_id, the stored audio_uri and the transcript.
    status, body = draft_for(
        app.client,
        f"{CASE}.m05.q1",
        "operating_surgeon",
        mode="voice",
        text=heard["text"],
        lang=heard["lang"],
        answer_id=answer_id,
        audio_uri=heard["audio_uri"],
    )
    assert status == 200, body
    assert body["answer_id"] == answer_id
    sent_extract = app.wire.json_bodies(EXTRACT)[-1]
    assert sent_extract["answer"]["answer_id"] == answer_id
    assert sent_extract["answer"]["mode"] == "voice"
    assert sent_extract["answer"]["audio_uri"] == heard["audio_uri"]
    assert sent_extract["answer"]["text"] == heard["text"]


def test_c5_an_unknown_stored_answer_is_not_served(answer_app, data_dir):
    """Criterion 5: only stored answers are served; nothing else through `/media/answers/`."""
    app = answer_app(data_dir)
    assert app.client.get(f"/media/answers/{uuid7()}.webm").status_code == 404
    assert app.client.get("/media/answers/..%2Fapp.db").status_code == 404


@pytest.mark.parametrize(
    ("role", "qid"),
    [
        ("operating_surgeon", f"{CASE}.m01.r1"),
        ("reviewer", f"{CASE}.m01.q1"),
        ("narrator", f"{CASE}.m01.q1"),
        ("ai", f"{CASE}.m01.r1"),
    ],
)
def test_c5_the_answerer_role_must_match_the_question_style(
    answer_app, data_dir, draft_for, role, qid
):
    """Criterion 5 (D-066: "an operating_surgeon answers only .qN, a reviewer only .rN …; ai,
    dataset and narrator … don't answer questions. A failure is 400 bad_request")."""
    app = answer_app(data_dir)
    status, body = draft_for(app.client, qid, role)
    assert status == 400, body
    assert body["error"]["code"] == "bad_request"


@pytest.mark.parametrize("qid", [f"{CASE}.m01.q1", f"{CASE}.m01.r1"])
def test_c5_role_play_may_answer_either_style(answer_app, data_dir, draft_for, qid):
    """Criterion 5 (D-066: "role-play and experts either")."""
    app = answer_app(data_dir)
    status, body = draft_for(app.client, qid, "dev_team_simulated")
    assert status == 200, body
    assert body["extract"]["draft"]["provenance"]["trust_label"] == "simulated"


@pytest.mark.parametrize(
    "qid", [f"{CASE}.m01.q9", f"{CASE}.m09.q1", "case-other-01.m01.q1", f"{CASE}.m01"]
)
def test_c8_a_question_not_in_questions_json_is_refused(answer_app, data_dir, draft_for, qid):
    """Criterion 8 (D-071 "questions only from questions.json"; README answer-queue "never
    invented"): a draft for a question that isn't in the case's `questions.json` is refused and
    never reaches the Brain."""
    app = answer_app(data_dir)
    status, body = draft_for(app.client, qid)
    assert 400 <= status < 500, body
    assert body["error"]["code"] in ("bad_request", "not_found")
    assert app.wire.json_bodies(EXTRACT) == []


# --- criterion 7: edits through /translate, source: edit, confirm_draft(), trust label --------


@pytest.mark.parametrize("lang", ["ja", "en"])
def test_c7_an_edited_chip_and_a_filled_field_are_translated_and_grounded_as_edits(
    answer_app, data_dir, draft_for, lang
):
    """Criterion 7 (plan §4.3, brain_api.md "On Confirm", D-056): "An edited or filled field goes
    through /translate; the stored record has both ja and en non-empty for it and a grounding with
    source: edit quoting the surgeon's words"."""
    app = answer_app(data_dir)
    status, body = draft_for(
        app.client, f"{CASE}.m05.q1", "operating_surgeon", text="Lens fogged", lang="en"
    )
    assert status == 200, body
    extract = body["extract"]
    assert [c["field"] for c in extract["chips"]] == ["situation_cue.text"]
    assert "action.text" in extract["missing_fields"]

    edited = "視界が白く曇った" if lang == "ja" else "The view went white"
    filled = "カメラを抜いて拭いた" if lang == "ja" else "Took the camera out and wiped it"
    response = _confirm(
        app.client,
        body,
        [
            {"field": "situation_cue.text", "text": edited, "lang": lang},
            {"field": "action.text", "text": filled, "lang": lang},
        ],
    )
    assert response.status_code == 201, response.text
    record = DecisionRecord.model_validate(response.json()["record"]).model_dump(mode="json")

    other = "en" if lang == "ja" else "ja"
    translated = app.wire.json_bodies("/v1/translate")
    sent_texts = [t for call in translated for t in call["texts"]]
    assert {"text": edited, "from_lang": lang} in sent_texts
    assert {"text": filled, "from_lang": lang} in sent_texts

    for path, words in (("situation_cue.text", edited), ("action.text", filled)):
        value = (
            record["situation_cue"]["text"]
            if path.startswith("situation")
            else record["action"]["text"]
        )
        assert value[lang] == words
        assert value[other].strip()
        edits = [g for g in record["grounding"] if g["field"] == path and g["source"] == "edit"]
        assert len(edits) == 1, record["grounding"]
        assert edits[0]["quote"] == words
        # The AI's reading no longer grounds an edited field.
        assert all(g["source"] == "edit" for g in record["grounding"] if g["field"] == path)


def test_c7_an_optional_missing_field_filled_in_is_bilingual_and_grounded(
    answer_app, data_dir, draft_for
):
    """Criterion 7: a filled `missing_fields` entry other than cue/action (here `reason`) gets both
    languages and a `source: edit` grounding."""
    app = answer_app(data_dir)
    status, body = draft_for(
        app.client, f"{CASE}.m05.q1", "operating_surgeon", text="レンズが曇った"
    )
    assert status == 200, body
    assert "reason" in body["extract"]["missing_fields"]
    edits = _fill_required(body["extract"]["draft"]) + [
        {"field": "reason", "text": "視野がないと安全に進めないから", "lang": "ja"}
    ]
    response = _confirm(app.client, body, edits)
    assert response.status_code == 201, response.text
    record = response.json()["record"]
    assert record["reason"]["ja"] == "視野がないと安全に進めないから"
    assert record["reason"]["en"].strip()
    assert {
        "field": "reason",
        "quote": "視野がないと安全に進めないから",
        "source": "edit",
    } in record["grounding"]


def test_c7_confirm_is_refused_while_cue_or_action_is_null(answer_app, data_dir, draft_for):
    """Criterion 7 / D-054 ("confirm_draft() raises while either is null, so the app's Confirm
    stays disabled"): Confirm without filling `action.text` stores nothing."""
    app = answer_app(data_dir)
    status, body = draft_for(
        app.client, f"{CASE}.m05.q1", "operating_surgeon", text="レンズが曇った"
    )
    assert status == 200, body
    assert body["extract"]["draft"]["action"]["text"] is None
    before = app.client.get(f"/api/cases/{CASE}/records").json()["records"]
    for edits in ([], [{"field": "situation_cue.text", "text": "曇り", "lang": "ja"}]):
        response = _confirm(app.client, body, edits)
        assert response.status_code == 400, response.text
        assert response.json()["error"]["code"] == "bad_request"
    assert app.client.get(f"/api/cases/{CASE}/records").json()["records"] == before


@pytest.mark.parametrize(
    "field",
    ["provenance.trust_label", "provenance.confirmed_by", "id", "question_id", "case_id"],
)
def test_c7_an_edit_cannot_change_metadata_or_provenance(answer_app, data_dir, draft_for, field):
    """Criterion 7 with D-064 rule 3 (groundings only on decision content) and rule 5 (provenance):
    an "edit" of a metadata or provenance field is refused, nothing stored."""
    app = answer_app(data_dir)
    status, body = draft_for(
        app.client, f"{CASE}.m05.q1", "operating_surgeon", text="レンズが曇った"
    )
    assert status == 200, body
    before = app.client.get(f"/api/cases/{CASE}/records").json()["records"]
    edits = _fill_required(body["extract"]["draft"]) + [
        {"field": field, "text": "expert_validated", "lang": "en"}
    ]
    response = _confirm(app.client, body, edits)
    assert response.status_code == 400, response.text
    assert app.client.get(f"/api/cases/{CASE}/records").json()["records"] == before


@pytest.mark.parametrize(
    ("role", "qid", "label"),
    [
        ("operating_surgeon", f"{CASE}.m05.q1", "operating_surgeon"),
        ("reviewer", f"{CASE}.m04.r1", "reviewer"),
        ("dev_team_simulated", f"{CASE}.m05.q1", "simulated"),
        ("dev_team_simulated", f"{CASE}.m02.r1", "simulated"),
    ],
)
def test_c7_the_trust_label_follows_the_answerer_role(
    answer_app, data_dir, draft_for, role, qid, label
):
    """Criterion 7 (plan §4.3 "trust_label follows the answerer: operating_surgeon, reviewer, or
    simulated for role-play"): 🩺 / 👁️ / 🧪, `attributed_to` = the role, stored as such."""
    app = answer_app(data_dir)
    status, body = draft_for(app.client, qid, role, text="Clipped the vessel early", lang="en")
    assert status == 200, body
    response = _confirm(app.client, body, _fill_required(body["extract"]["draft"], "en"))
    assert response.status_code == 201, response.text
    record = response.json()["record"]
    assert record["provenance"]["trust_label"] == label
    assert record["provenance"]["attributed_to"] == role
    assert record["question_id"] == qid
    stored = {
        r["record"]["id"]: r["record"]
        for r in app.client.get(f"/api/cases/{CASE}/records").json()["records"]
    }
    assert stored[record["id"]]["provenance"]["trust_label"] == label


def test_c7_unedited_fields_keep_the_drafts_values_and_groundings(answer_app, data_dir, draft_for):
    """Criterion 7 / D-056 "nothing is filled for the surgeon": Confirm adds only what the surgeon
    typed; every other field and grounding of the draft is stored as drafted."""
    app = answer_app(data_dir)
    status, body = draft_for(
        app.client, f"{CASE}.m05.q1", "operating_surgeon", text="レンズが曇った"
    )
    assert status == 200, body
    draft = copy.deepcopy(body["extract"]["draft"])
    response = _confirm(
        app.client, body, [{"field": "action.text", "text": "拭いた", "lang": "ja"}]
    )
    assert response.status_code == 201, response.text
    record = response.json()["record"]
    for key in (
        "situation_cue",
        "obstacle",
        "anticipation",
        "alternatives",
        "reason",
        "immediate_result",
        "context",
        "evidence",
        "kind",
        "step_id",
        "moment_id",
        "language",
    ):
        assert record[key] == draft[key], key
    for grounding in draft["grounding"]:
        assert grounding in record["grounding"]
    assert record["reason"] is None and record["anticipation"] is None


# --- criterion 8 (server): the queue comes from questions.json ------------------------------------


@pytest.mark.parametrize("role", ["operating", "reviewer"])
def test_c8_the_answer_queue_is_questions_json(answer_app, data_dir, fixture_docs, role):
    """Criterion 8 (README answer-queue: "the questions from questions.json (never invented), each
    with its moment, clip, poster and answered; est_seconds of the unanswered ones")."""
    app = answer_app(data_dir)
    response = app.client.get(f"/api/cases/{CASE}/answer-queue", params={"role": role})
    assert response.status_code == 200, response.text
    queue = response.json()
    expected = fixture_docs["questions"][role]
    assert [item["question"]["id"] for item in queue["questions"]] == [q["id"] for q in expected]
    for item, question in zip(queue["questions"], expected, strict=True):
        _same(Question, item["question"], question)
        _same(Moment, item["moment"], _moment(fixture_docs, question["moment_id"]))
        assert item["answered"] is False
        for key in ("clip", "poster"):
            assert app.client.get(item[key]).status_code in (200, 206), item[key]
        assert item["clip"].endswith(f"{question['moment_id']}.mp4")
    assert queue["est_seconds"] == pytest.approx(sum(q["est_seconds"] for q in expected))


def test_c8_a_confirmed_answer_marks_its_question_answered(
    answer_app, data_dir, draft_for, fixture_docs
):
    """Criterion 8: the queue's `answered` and `est_seconds` follow the store (README)."""
    app = answer_app(data_dir)
    status, body = draft_for(
        app.client, f"{CASE}.m05.q1", "operating_surgeon", text="レンズが曇った"
    )
    assert status == 200, body
    assert _confirm(app.client, body, _fill_required(body["extract"]["draft"])).status_code == 201
    queue = app.client.get(f"/api/cases/{CASE}/answer-queue", params={"role": "operating"}).json()
    answered = {item["question"]["id"]: item["answered"] for item in queue["questions"]}
    assert answered[f"{CASE}.m05.q1"] is True
    assert sum(answered.values()) == 1
    total = sum(q["est_seconds"] for q in fixture_docs["questions"]["operating"])
    m05 = _question(fixture_docs, f"{CASE}.m05.q1")["est_seconds"]
    assert queue["est_seconds"] == pytest.approx(total - m05)
