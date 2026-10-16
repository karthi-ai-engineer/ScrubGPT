"""The fake Brain's deterministic answers (plan §4.5, D-037). No network, no API key, no randomness.

Every function returns a contract response model, so the fake Brain can't send a shape the real
Brain wouldn't. Texts the fake Brain makes up are marked as mock texts in both languages.
"""

import hashlib
import math
import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from scrubgpt_contracts.models.brain_api import (
    Answer,
    AskRequest,
    AskResponse,
    BrainMode,
    BriefingRequest,
    BriefingResponse,
    BriefingSection,
    CacheMode,
    Chip,
    Citation,
    Coverage,
    EmbedRequest,
    EmbedResponse,
    ExtractRequest,
    ExtractResponse,
    HealthResponse,
    HealthStatus,
    LangHint,
    TranscribeForm,
    TranscribeResponse,
    TranslateRequest,
    TranslateResponse,
    Verdict,
)
from scrubgpt_contracts.models.case_package import MomentKind, SeedRecords
from scrubgpt_contracts.models.common import (
    CONTRACT_VERSION,
    Bilingual,
    GeneratedBy,
    Lang,
    MediaEvidence,
    Role,
    TrustLabel,
    get_at_path,
    media_fragment,
)
from scrubgpt_contracts.models.decision_record import (
    DecisionRecord,
    DecisionRecordDraft,
    DraftProvenance,
    RecordKind,
)
from scrubgpt_contracts.models.reference import ProcedureReference

AnyRecord = DecisionRecord | DecisionRecordDraft

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures"
FIXTURE_CASE_DIR = FIXTURES_DIR / "cases" / "case-fixture-01"
FIXTURE_REFERENCE = FIXTURES_DIR / "reference" / "rarp.json"

EMBED_DIM = 256
EMBED_MODEL = "mock-hash-256"
MATCH_THRESHOLD = 0.3
"""Cosine score at or above which a candidate counts as matching (D-037)."""
MAX_CITATIONS = 3

MOCK = GeneratedBy(model_tier="TEXT_SMART", model="mock", prompt_version="extract.mock.v1")
MODEL_TIERS = (
    "VISION_FAST",
    "VISION_DEEP",
    "TEXT_SMART",
    "TEXT_FAST",
    "STT",
    "STT_DIARIZE",
    "TTS",
    "EMBED",
)

TRANSCRIPTS = {
    Lang.JA: "静脈性の出血だったので、まず気腹圧を上げて様子を見ました。",
    Lang.EN: "The bleeding was venous, so I first raised the insufflation pressure and watched.",
}
"""The fixed transcript per language; `lang_hint=auto` gives the Japanese one (D-037)."""

TRUST_BY_ROLE = {
    Role.AI: TrustLabel.AI_DETECTED,
    Role.DATASET: TrustLabel.DATASET_ANNOTATION,
    Role.NARRATOR: TrustLabel.NARRATION_EXTRACTED,
    Role.OPERATING_SURGEON: TrustLabel.OPERATING_SURGEON,
    Role.REVIEWER: TrustLabel.REVIEWER,
    Role.EXPERT: TrustLabel.EXPERT_VALIDATED,
    Role.DEV_TEAM_SIMULATED: TrustLabel.SIMULATED,
}
"""The draft's trust label follows the answerer (§4.3)."""

KIND_BY_MOMENT = {
    MomentKind.EVENT: RecordKind.RESCUE,
    MomentKind.CHECKPOINT: RecordKind.CHECKPOINT,
    MomentKind.DEVIATION: RecordKind.ANTICIPATORY,
    MomentKind.SPEECH: RecordKind.ANTICIPATORY,
}


# ── /health and /transcribe ───────────────────────────────────────────────────


def health() -> HealthResponse:
    return HealthResponse(
        contract_version=CONTRACT_VERSION,
        status=HealthStatus.OK,
        mode=BrainMode.MOCK,
        model_tiers={tier: "mock" for tier in MODEL_TIERS},
        cache_mode=CacheMode.OFF,
    )


def transcribe(form: TranscribeForm) -> TranscribeResponse:
    lang = Lang.EN if form.lang_hint is LangHint.EN else Lang.JA
    return TranscribeResponse(contract_version=CONTRACT_VERSION, text=TRANSCRIPTS[lang], lang=lang)


# ── /translate ────────────────────────────────────────────────────────────────


def mock_bilingual(text: str, lang: Lang) -> Bilingual:
    """`text` verbatim in its own half; a marked mock translation in the other half."""
    if lang is Lang.JA:
        return Bilingual(ja=text, en=f"[mock translation] {text}")
    return Bilingual(ja=f"［模擬翻訳］{text}", en=text)


def translate(request: TranslateRequest) -> TranslateResponse:
    items = [mock_bilingual(item.text, item.from_lang) for item in request.texts]
    return TranslateResponse(contract_version=CONTRACT_VERSION, items=items)


# ── /embed ────────────────────────────────────────────────────────────────────

_TOKEN = re.compile(r"[a-z0-9]+|[々぀-ヿ㐀-鿿豈-﫿]+")


def tokens(text: str) -> list[str]:
    """NFKC + lowercase; Latin word tokens and CJK character bigrams (a lone CJK character is its
    own token)."""
    out: list[str] = []
    for run in _TOKEN.findall(unicodedata.normalize("NFKC", text).lower()):
        if run.isascii():
            out.append(run)
        elif len(run) == 1:
            out.append(run)
        else:
            out += [run[i : i + 2] for i in range(len(run) - 1)]
    return out


def embed_text(text: str) -> list[float]:
    """blake2b of each token → one of 256 buckets; L2-normalised. No tokens → the zero vector."""
    vector = [0.0] * EMBED_DIM
    for token in tokens(text):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        vector[int.from_bytes(digest, "big") % EMBED_DIM] += 1.0
    norm = math.sqrt(sum(x * x for x in vector))
    return [x / norm for x in vector] if norm else vector


def embed(request: EmbedRequest) -> EmbedResponse:
    return EmbedResponse(
        contract_version=CONTRACT_VERSION,
        vectors=[embed_text(text) for text in request.texts],
        dim=EMBED_DIM,
        model=EMBED_MODEL,
    )


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


# ── /ask and /briefing ────────────────────────────────────────────────────────


def record_text(record: DecisionRecord) -> str:
    """The searchable text of a record, in both languages."""
    parts: list[str] = [*record.situation_cue.cue_terms]
    texts: list[Bilingual | None] = [
        record.situation_cue.text,
        record.anticipation,
        record.action.text,
        record.reason,
        record.immediate_result,
        *record.context.patient_factors,
        *(alternative.option for alternative in record.alternatives),
    ]
    for item in texts:
        if item is not None:
            parts += [item.ja, item.en]
    if record.obstacle is not None:
        parts.append(record.obstacle.type or record.obstacle.family.value)
    return "\n".join(parts)


@dataclass(frozen=True)
class Scored:
    score: float
    position: int
    record: DecisionRecord


def rank(query: str, candidates: Iterable[DecisionRecord]) -> list[Scored]:
    """Candidates by cosine score, highest first; ties keep the order they were sent in."""
    q = embed_text(query)
    scored = [
        Scored(cosine(q, embed_text(record_text(record))), i, record)
        for i, record in enumerate(candidates)
    ]
    return sorted(scored, key=lambda s: (-s.score, s.position))


def _citation(record: DecisionRecord) -> Citation:
    media = [i for i, item in enumerate(record.evidence) if isinstance(item, MediaEvidence)]
    return Citation(record_id=record.id, evidence_index=media[0] if media else None)


def _summary(record: DecisionRecord) -> Bilingual:
    return Bilingual(
        ja=f"{record.situation_cue.text.ja} → {record.action.text.ja}",
        en=f"{record.situation_cue.text.en} → {record.action.text.en}",
    )


def ask(request: AskRequest) -> AskResponse:
    """Coverage: `full` if 2 or more candidates score ≥ 0.3, `partial` if 1, `none` if 0 (D-037).
    Cites the top-ranked matching candidates (at most 3)."""
    matched = [s for s in rank(request.query, request.candidates) if s.score >= MATCH_THRESHOLD]
    coverage = (
        Coverage.FULL if len(matched) >= 2 else Coverage.PARTIAL if matched else Coverage.NONE
    )
    cited = [s.record for s in matched[:MAX_CITATIONS]]
    if not cited:
        answer = Bilingual(
            ja="（模擬回答）この質問に合う過去の記録は、知識ベースに見つかりませんでした。",
            en="(Mock answer) No past records in the knowledge base match this question.",
        )
    else:
        lines = [_summary(record) for record in cited]
        answer = Bilingual(
            ja=f"（模擬回答）過去の記録{len(matched)}件がこの質問に合います。"
            + "".join(f"\n[{i}] {line.ja}" for i, line in enumerate(lines, 1)),
            en=f"(Mock answer) {len(matched)} past record(s) match this question."
            + "".join(f"\n[{i}] {line.en}" for i, line in enumerate(lines, 1)),
        )
    return AskResponse(
        contract_version=CONTRACT_VERSION,
        answer=answer,
        citations=[_citation(record) for record in cited],
        coverage=coverage,
    )


@cache
def reference() -> ProcedureReference:
    return ProcedureReference.model_validate_json(FIXTURE_REFERENCE.read_bytes())


def _family_name(family: str | None) -> Bilingual:
    if family is not None:
        for entry in reference().obstacle_taxonomy:
            if entry.id.value == family:
                return entry.name
    return Bilingual(ja="障害の記録なし", en="No obstacle recorded")


def briefing(request: BriefingRequest) -> BriefingResponse:
    """A section for the case factors (if any), then one per obstacle family among the
    candidates, with counts. Retrieval of past cases only: no advice and no percentages."""
    sections: list[BriefingSection] = []
    if request.case_factors:
        sections.append(
            BriefingSection(
                title=Bilingual(ja="今回の症例の要素", en="Factors of this case"),
                body=Bilingual(
                    ja="、".join(f.ja for f in request.case_factors),
                    en=", ".join(f.en for f in request.case_factors),
                ),
                citations=[],
            )
        )
    query = "\n".join(f"{f.ja}\n{f.en}" for f in request.case_factors)
    ordered = [s.record for s in rank(query, request.candidates)] if query else request.candidates
    groups: dict[str | None, list[DecisionRecord]] = {}
    for record in ordered:
        family = record.obstacle.family.value if record.obstacle is not None else None
        groups.setdefault(family, []).append(record)
    # With case factors, the family of the best-matching record comes first; without, the
    # family with the most records (ties keep the order the candidates were sent in).
    order = groups.items() if query else sorted(groups.items(), key=lambda kv: -len(kv[1]))
    for family, records in order:
        name = _family_name(family)
        lines = [_summary(record) for record in records]
        sections.append(
            BriefingSection(
                title=name,
                body=Bilingual(
                    ja=f"（模擬）過去の記録{len(records)}件："
                    + "".join(f"\n・{line.ja}" for line in lines),
                    en=f"(Mock) {len(records)} past record(s):"
                    + "".join(f"\n- {line.en}" for line in lines),
                ),
                citations=[_citation(record) for record in records],
            )
        )
    if not request.candidates:
        sections.append(
            BriefingSection(
                title=Bilingual(ja="過去の症例", en="Past cases"),
                body=Bilingual(
                    ja="（模擬）知識ベースに参考になる過去の記録はありません。",
                    en="(Mock) The knowledge base has no past records to show.",
                ),
                citations=[],
            )
        )
    return BriefingResponse(contract_version=CONTRACT_VERSION, sections=sections)


# ── /extract ──────────────────────────────────────────────────────────────────


@cache
def seed_records() -> tuple[DecisionRecord, ...]:
    path = FIXTURE_CASE_DIR / "seed_records.json"
    return tuple(SeedRecords.model_validate_json(path.read_bytes()).records)


def _canned(request: ExtractRequest) -> DecisionRecord | None:
    """The fixture record for the question's moment (or, for a record tied to no moment, its
    step) in the answer's language, or `None`.

    Only the same language (D-054): a record's quotes must be in the language the surgeon
    answered in, so an answer in another language gets the generic draft.
    """
    moment = request.moment
    matches = [
        r
        for r in seed_records()
        if r.case_id == request.case_context.case.id
        and r.language is request.answer.lang
        and (r.moment_id == moment.id or (r.moment_id is None and r.step_id == moment.step_id))
    ]
    return matches[0] if matches else None


def _provenance(role: Role) -> DraftProvenance:
    return DraftProvenance(
        trust_label=TRUST_BY_ROLE[role],
        attributed_to=role,
        generated_by=MOCK,
        confirmed_by=None,
        confirmed_at=None,
    )


def _draft_from_record(record: DecisionRecord, request: ExtractRequest) -> DecisionRecordDraft:
    data = record.model_dump(mode="json", by_alias=True)
    data["id"] = None
    data["moment_id"] = request.moment.id
    data["provenance"] = _provenance(request.answerer_role).model_dump(mode="json")
    for item in data["evidence"]:
        if "answer_id" in item:
            item["answer_id"] = str(request.answer.answer_id)
    return DecisionRecordDraft.model_validate(data)


def _answer_text(question_tap_labels: dict[str, Bilingual], request: ExtractRequest) -> str | None:
    """What the surgeon said, verbatim: the text, else the tap options chosen, else the AI draft
    or quote they confirmed."""
    answer: Answer = request.answer
    lang = answer.lang.value
    if answer.text is not None:
        return answer.text
    if answer.tap is None:  # pragma: no cover (Answer requires text unless it is a tap)
        return None
    if answer.tap.choice_ids:
        sep = "、" if answer.lang is Lang.JA else ", "
        return sep.join(getattr(question_tap_labels[c], lang) for c in answer.tap.choice_ids)
    if answer.tap.verdict is Verdict.CONFIRM:
        confirmed = request.question.ai_draft or (
            request.question.quote.text if request.question.quote is not None else None
        )
        return getattr(confirmed, lang) if confirmed is not None else None
    return None


def _generic_draft(request: ExtractRequest) -> DecisionRecordDraft:
    """A draft built only from the request: the answer becomes the action, the flagged moment
    the cue, and everything the surgeon didn't state stays null."""
    moment = request.moment
    answer = request.answer
    labels = {option.id: option.label for option in request.question.tap_options}
    said = _answer_text(labels, request)
    rejected = answer.tap is not None and answer.tap.verdict is Verdict.REJECT and said is None
    if said is None:
        action = Bilingual(ja="（模擬）AIの下書きを却下", en="(Mock) Rejected the AI draft")
    else:
        action = mock_bilingual(said, answer.lang)
    evidence: list[dict] = [
        {
            "kind": "media",
            "case_id": request.case_context.case.id,
            "uri": media_fragment("video.mp4", moment.t_start, moment.t_end),
            "t_start": moment.t_start,
            "t_end": moment.t_end,
        }
    ]
    grounding: list[dict] = []
    if said is not None:
        evidence.append({"kind": "answer_text", "answer_id": str(answer.answer_id), "quote": said})
        source = (
            "edit" if answer.tap is not None and answer.tap.verdict is Verdict.EDIT else "answer"
        )
        grounding.append({"field": "action.text", "quote": said, "source": source})
    if answer.audio_uri is not None:
        evidence.append(
            {"kind": "answer_audio", "answer_id": str(answer.answer_id), "uri": answer.audio_uri}
        )
    data = {
        "contract_version": CONTRACT_VERSION,
        "id": None,
        "case_id": request.case_context.case.id,
        "moment_id": moment.id,
        "step_id": moment.step_id,
        "language": answer.lang.value,
        "kind": KIND_BY_MOMENT[moment.kind].value,
        "context": {"patient_factors": [], "preop_plan": None},
        "situation_cue": {"text": moment.title.model_dump(), "cue_terms": []},
        "obstacle": None,
        "anticipation": None,
        "action": {"type": "act", "text": action.model_dump(), "actor": "surgeon"},
        "alternatives": [],
        "reason": None,
        "immediate_result": None,
        "delayed_outcome": {"status": "pending", "text": None, "source": None},
        "evidence": evidence,
        "grounding": grounding,
        "provenance": _provenance(request.answerer_role).model_dump(mode="json"),
        "new_terms": [],
        "confidence": 0.2 if rejected else 0.5,
    }
    return DecisionRecordDraft.model_validate(data)


CHIP_PATHS = ("situation_cue.text", "anticipation", "action.text", "reason", "immediate_result")
OPTIONAL_PATHS = ("context.preop_plan", "obstacle", "anticipation", "reason", "immediate_result")


def chip_paths(draft: AnyRecord) -> list[str]:
    """Every filled Bilingual field the surgeon can confirm or edit, in reading order."""
    paths = [f"context.patient_factors[{i}]" for i in range(len(draft.context.patient_factors))]
    if draft.context.preop_plan is not None:
        paths.append("context.preop_plan")
    for path in CHIP_PATHS:
        if get_at_path(draft, path) is not None:
            paths.append(path)
    for i, alternative in enumerate(draft.alternatives):
        paths.append(f"alternatives[{i}].option")
        if alternative.why_not is not None:
            paths.append(f"alternatives[{i}].why_not")
    return paths


def missing_paths(draft: AnyRecord) -> list[str]:
    """Fields the surgeon did not state."""
    missing = [path for path in OPTIONAL_PATHS if get_at_path(draft, path) is None]
    if not draft.alternatives:
        missing.append("alternatives")
    return missing


def readback(draft: AnyRecord) -> Bilingual:
    ja = [f"状況：{draft.situation_cue.text.ja}", f"対応：{draft.action.text.ja}"]
    en = [f"Cue: {draft.situation_cue.text.en}", f"Action: {draft.action.text.en}"]
    if draft.reason is not None:
        ja.append(f"理由：{draft.reason.ja}")
        en.append(f"Reason: {draft.reason.en}")
    return Bilingual(ja="。".join(ja) + "。", en=". ".join(en) + ".")


def extract(request: ExtractRequest) -> ExtractResponse:
    """The fixture record for the question's moment when there is one (D-037), else a generic
    draft built from the answer."""
    canned = _canned(request)
    draft = _draft_from_record(canned, request) if canned is not None else _generic_draft(request)
    chips = [
        Chip(field=path, value=get_at_path(draft, path), editable=True)
        for path in chip_paths(draft)
    ]
    return ExtractResponse(
        contract_version=CONTRACT_VERSION,
        draft=draft,
        readback=readback(draft),
        chips=chips,
        missing_fields=missing_paths(draft),
    )
