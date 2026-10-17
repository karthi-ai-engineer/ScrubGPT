import { useMemo, useState } from "react";

import type { DecisionRecord } from "@contracts/contracts";

import { useServerEvent } from "@/api/events";
import { useCaseRecords } from "@/api/hooks";
import type { CaseDetail } from "@/api/types";

/**
 * The case's Decision Records for the J8 graph, growing live (D-071): the stored records from
 * `GET /api/cases/{id}/records` (seed + confirmed answers; the package's seed records until they
 * load, or if the store can't be read), plus every `record.created` of this case that arrives
 * over SSE. Records are kept apart by id: two records on one moment stay two records.
 */
export function useLiveRecords(detail: CaseDetail): readonly DecisionRecord[] {
  const caseId = detail.case.id;
  const stored = useCaseRecords(caseId);
  const [live, setLive] = useState<DecisionRecord[]>([]);

  useServerEvent("record.created", ({ record }) => {
    if (record.case_id !== caseId) return;
    setLive((current) => (current.some((r) => r.id === record.id) ? current : [...current, record]));
  });

  const base = stored.data ?? detail.seed_records.records;
  return useMemo(() => {
    const seen = new Set(base.map((r) => r.id));
    const added = live.filter((r) => !seen.has(r.id));
    return added.length === 0 ? base : [...base, ...added];
  }, [base, live]);
}
