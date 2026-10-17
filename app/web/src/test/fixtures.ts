/**
 * Test data built from the real contract fixture case (contracts/fixtures/cases/case-fixture-01),
 * shaped like the app server's responses.
 */
import { vi } from "vitest";

import type { Case, Metrics, Moments, Questions, SeedRecords, Timeline } from "@contracts/contracts";

import caseJson from "../../../../contracts/fixtures/cases/case-fixture-01/case.json";
import metricsJson from "../../../../contracts/fixtures/cases/case-fixture-01/metrics.json";
import momentsJson from "../../../../contracts/fixtures/cases/case-fixture-01/moments.json";
import questionsJson from "../../../../contracts/fixtures/cases/case-fixture-01/questions.json";
import seedRecordsJson from "../../../../contracts/fixtures/cases/case-fixture-01/seed_records.json";
import timelineJson from "../../../../contracts/fixtures/cases/case-fixture-01/timeline.json";

import type { CaseDetail, CaseSummary } from "@/api/types";

export const fixtureCase = caseJson as Case;
const moments = momentsJson as Moments;
const questions = questionsJson as Questions;
const seedRecords = seedRecordsJson as SeedRecords;

export const fixtureSummary: CaseSummary = {
  case: fixtureCase,
  media: {
    video: `/media/cases/${fixtureCase.id}/video.mp4`,
    poster: `/media/cases/${fixtureCase.id}/poster.jpg`,
  },
  counts: {
    moments: moments.moments.length,
    operating_questions: questions.operating.length,
    reviewer_questions: questions.reviewer.length,
    seed_records: seedRecords.records.length,
  },
  // Distinct labels of the fixture package, in enum order.
  trust_labels: ["ai_detected", "dataset_annotation", "narration_extracted", "simulated"],
  has_metrics: true,
};

export const fixtureDetail: CaseDetail = {
  ...fixtureSummary,
  timeline: timelineJson as Timeline,
  moments,
  questions,
  seed_records: seedRecords,
  metrics: metricsJson as Metrics,
};

type Route = (url: string) => { status: number; body: unknown } | undefined;

/** Replaces `fetch` with a router of canned JSON responses; unknown URLs get a 404 `ApiError`. */
export function mockFetch(route: Route) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const hit = route(url) ?? {
      status: 404,
      body: { contract_version: "1.0", error: { code: "not_found", message: `no route ${url}`, retryable: false } },
    };
    return new Response(JSON.stringify(hit.body), {
      status: hit.status,
      headers: { "Content-Type": "application/json" },
    });
  });
}
