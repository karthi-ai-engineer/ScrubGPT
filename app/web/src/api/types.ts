/**
 * App-server response shapes (app-internal, not contracts). They are composed only
 * from generated contract types; never redefine a contract type here.
 */
import type {
  Answer,
  Case,
  DecisionRecord,
  DecisionRecordDraft,
  ExtractResponse,
  Lang,
  Metrics,
  Moment,
  Moments,
  Question,
  Questions,
  Role,
  SeedRecords,
  Timeline,
  TrustLabel,
} from "@contracts/contracts";

/** URLs of a case's media files, served by the app server under `/media/`. */
export interface CaseMedia {
  /** e.g. `/media/cases/case-fixture-01/video.mp4` */
  video: string;
  /** e.g. `/media/cases/case-fixture-01/poster.jpg` */
  poster: string;
}

export interface CaseCounts {
  moments: number;
  operating_questions: number;
  reviewer_questions: number;
  seed_records: number;
}

/** One entry of `GET /api/cases`. */
export interface CaseSummary {
  case: Case;
  media: CaseMedia;
  counts: CaseCounts;
  /** Distinct labels in the package (timeline items, moments, seed records), in enum order. */
  trust_labels: TrustLabel[];
  has_metrics: boolean;
}

/** `GET /api/cases` (case-id order). */
export interface CasesResponse {
  cases: CaseSummary[];
}

/** `GET /api/cases/{case_id}`. */
export interface CaseDetail extends CaseSummary {
  timeline: Timeline;
  moments: Moments;
  questions: Questions;
  seed_records: SeedRecords;
  metrics: Metrics | null;
}

/** `GET /api/health`. */
export interface AppHealth {
  status: string;
  contract_version: string;
  brain_mode: string;
  cases: { loaded: number; rejected: number };
}

/** Operating-surgeon and reviewer question counts, counted by the server from `questions.json`. */
export interface QuestionCounts {
  operating: number;
  reviewer: number;
}

/**
 * The `case.ended` SSE event (app/server README "SSE events"), also returned by
 * `POST /api/cases/{case_id}/replay-ended`.
 */
export interface CaseEndedEvent {
  case_id: string;
  questions: QuestionCounts;
  /** Sum of the operating questions' `est_seconds`. */
  est_seconds: number;
}

// ── Answer app (J3) and the knowledge store (I2) ─────────────────────────────

/** Which question list: the operating surgeon's (`…qN`) or reviewers' (`…rN`). */
export type QueueRole = "operating" | "reviewer";

/** One question of `GET /api/cases/{case_id}/answer-queue`, with its moment and media URLs. */
export interface AnswerQueueItem {
  question: Question;
  moment: Moment;
  /** e.g. `/media/cases/case-fixture-01/clips/case-fixture-01.m01.mp4` */
  clip: string;
  poster: string;
  /** The store already holds a record answering this question. */
  answered: boolean;
}

/** `GET /api/cases/{case_id}/answer-queue?role=operating|reviewer` (questions only from `questions.json`). */
export interface AnswerQueue {
  case_id: string;
  role: QueueRole;
  /** Sum of the unanswered questions' `est_seconds`. */
  est_seconds: number;
  questions: AnswerQueueItem[];
}

/** One record of `GET /api/cases/{case_id}/records`. */
export interface StoredRecord {
  record: DecisionRecord;
  source: "seed" | "answer";
  answer_id: string | null;
  stored_at: string;
}

export interface RecordsResponse {
  records: StoredRecord[];
}

/** `POST /api/answers/audio`: the server's `answer_id`, where it kept the file, the transcript. */
export interface AudioAnswer {
  answer_id: string;
  audio_uri: string;
  text: string;
  lang: Lang;
}

/** The contract `Answer`, except that the server assigns `answer_id` when it is missing. */
export type DraftAnswer = Omit<Answer, "answer_id"> & { answer_id?: string };

/** `POST /api/answers/draft` body. */
export interface DraftRequest {
  case_id: string;
  question_id: string;
  answerer_role: Role;
  answer: DraftAnswer;
}

/** `POST /api/answers/draft` response. */
export interface DraftResponse {
  answer_id: string;
  extract: ExtractResponse;
}

/** The surgeon's own words for one draft field (a chip edit or a filled missing field). */
export interface FieldEdit {
  field: string;
  text: string;
  lang: Lang;
}

/** `POST /api/answers/confirm` body. */
export interface ConfirmRequest {
  answer_id: string;
  draft: DecisionRecordDraft;
  edits: FieldEdit[];
  confirmed_by: string;
}

/** `POST /api/answers/confirm` response (201). */
export interface ConfirmResponse {
  record: DecisionRecord;
}

/** The `answer.confirmed` SSE event (first of three on Confirm). */
export interface AnswerConfirmedEvent {
  case_id: string;
  question_id: string | null;
  record_id: string;
  answer_id: string;
}

/** The `record.created` SSE event (second): the stored Decision Record. */
export interface RecordCreatedEvent {
  record: DecisionRecord;
}

/** The `graph.updated` SSE event (third): what the record added to the knowledge graph. */
export interface GraphUpdatedEvent {
  case_id: string;
  nodes: { id: string; kind: string }[];
  edges: { src: string; dst: string; kind: string; record_id: string; trust_label: TrustLabel }[];
}
