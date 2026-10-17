/**
 * App-server response shapes (app-internal, not contracts). They are composed only
 * from generated contract types; never redefine a contract type here.
 */
import type {
  Case,
  Metrics,
  Moments,
  Questions,
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
