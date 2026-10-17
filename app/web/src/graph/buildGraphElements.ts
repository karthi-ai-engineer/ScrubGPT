/**
 * J8 graph panel: the knowledge graph of a case as it is revealed by the replay (pure; only
 * `GraphPanel` touches Cytoscape).
 *
 * Nodes: the case; each reached step (named from the Reference); each revealed moment (linked to
 * its step); the moment's `draft_obstacle` taxonomy leaf (Reference name); and the case's seed
 * Decision Records, **one node per record** (every viewpoint separate, never merged, D-069):
 * - a record with a revealed moment links to that moment;
 * - a record without a moment (or whose moment is not in the package) links to its step once
 *   that step is reached.
 * Every knowledge node carries its trust-label emoji; records also show their viewpoint
 * (`.qN` 🩺 operating surgeon's account, `.rN` 👁️ reviewer's interpretation). On the canvas a
 * record shows only these emoji; its action text is `detail` (hover/tap, node list).
 */
import type {
  DecisionRecord,
  Lang,
  Moment,
  ProcedureReference,
  StepSegment,
  TrustLabel,
} from "@contracts/contracts";

import type { CaseDetail } from "@/api/types";
import { buildReferenceLookup, phaseColor } from "@/lib/reference";
import { TRUST_EMOJI } from "@/lib/trust";

export type GraphNodeKind = "case" | "step" | "moment" | "obstacle" | "record";

/** Whose account a record is: from its `question_id` (`.qN` / `.rN`), else none (e.g. narration). */
export type Viewpoint = "operating" | "reviewer";

export interface GraphNode {
  id: string;
  kind: GraphNodeKind;
  /** The text drawn on the canvas (short; a record shows only its emoji). */
  label: string;
  /** The full text in the current language, shown on hover or tap and in the node list. */
  detail: string;
  /** The trust label of the knowledge behind the node; `null` for the case and Reference nodes. */
  trust: TrustLabel | null;
  /** Where clicking the node seeks the video (moments only). */
  tStart: number | null;
  viewpoint: Viewpoint | null;
  /** Fill colour hint (steps: their phase colour). */
  color: string | null;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
}

export interface GraphElements {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

/** What the replay has revealed so far (both already filtered by `t >= t_start`). */
export interface GraphReveal {
  /** Reached step segments of the shown track. */
  steps: readonly StepSegment[];
  /** Revealed moments. */
  moments: readonly Moment[];
}

export const VIEWPOINT_EMOJI: Readonly<Record<Viewpoint, string>> = {
  operating: "🩺",
  reviewer: "👁️",
};

const SHORT_TEXT = 22;
/** Longest canvas label text (code points) before it is cut with an ellipsis. */
const LABEL_TEXT = 30;

export function viewpointOf(record: Pick<DecisionRecord, "question_id">): Viewpoint | null {
  const id = record.question_id;
  if (!id) return null;
  if (/\.q\d+$/.test(id)) return "operating";
  if (/\.r\d+$/.test(id)) return "reviewer";
  return null;
}

/** Cuts `text` to `max` characters (by code point), adding an ellipsis. */
export function shorten(text: string, max = SHORT_TEXT): string {
  const chars = [...text.trim()];
  return chars.length <= max ? chars.join("") : `${chars.slice(0, max - 1).join("").trimEnd()}…`;
}

export const nodeId = {
  case: (id: string) => `case:${id}`,
  step: (stepId: string) => `step:${stepId}`,
  moment: (id: string) => `moment:${id}`,
  obstacle: (leafId: string) => `obstacle:${leafId}`,
  record: (id: string) => `record:${id}`,
};

export function buildGraphElements(
  detail: CaseDetail,
  reference: ProcedureReference | undefined,
  revealed: GraphReveal,
  lang: Lang,
): GraphElements {
  const lookup = buildReferenceLookup(reference);
  const nodes = new Map<string, GraphNode>();
  const edges = new Map<string, GraphEdge>();

  const addNode = (node: GraphNode) => {
    if (!nodes.has(node.id)) nodes.set(node.id, node);
  };
  const addEdge = (source: string, target: string) => {
    const id = `edge:${source}->${target}`;
    if (!edges.has(id)) edges.set(id, { id, source, target });
  };

  const caseId = nodeId.case(detail.case.id);
  addNode({
    id: caseId,
    kind: "case",
    label: shorten(detail.case.title[lang], LABEL_TEXT),
    detail: detail.case.title[lang],
    trust: null,
    tStart: null,
    viewpoint: null,
    color: null,
  });

  // Steps: one node per Reference step, from the first segment that reached it.
  const addStep = (stepId: string, trust: TrustLabel) => {
    const id = nodeId.step(stepId);
    if (nodes.has(id)) return id;
    const name = lookup.stepName(stepId)?.[lang] ?? stepId;
    addNode({
      id,
      kind: "step",
      label: `${TRUST_EMOJI[trust]} ${shorten(name, LABEL_TEXT)}`,
      detail: name,
      trust,
      tStart: null,
      viewpoint: null,
      color: phaseColor(lookup.phaseOrder(stepId)),
    });
    addEdge(caseId, id);
    return id;
  };
  for (const segment of revealed.steps) addStep(segment.step_id, segment.provenance.trust_label);
  const reachedSteps = new Set(revealed.steps.map((s) => s.step_id));

  // Moments (and their obstacle leaves). A moment can be revealed before the shown track reaches
  // its step (tracks disagree on boundaries); its step node is then added with the moment's label.
  const shownMoments = new Set<string>();
  for (const moment of revealed.moments) {
    const trust = moment.provenance.trust_label;
    const stepNode = addStep(moment.step_id, trust);
    const id = nodeId.moment(moment.id);
    addNode({
      id,
      kind: "moment",
      label: `${TRUST_EMOJI[trust]} ${shorten(moment.title[lang], LABEL_TEXT)}`,
      detail: moment.title[lang],
      trust,
      tStart: moment.t_start,
      viewpoint: null,
      color: null,
    });
    addEdge(stepNode, id);
    shownMoments.add(moment.id);

    const leaf = moment.draft_obstacle ? lookup.obstacle(moment.draft_obstacle) : undefined;
    if (leaf) {
      const obstacle = nodeId.obstacle(leaf.id);
      addNode({
        id: obstacle,
        kind: "obstacle",
        label: shorten(leaf.name[lang], LABEL_TEXT),
        detail: leaf.name[lang],
        trust: null,
        tStart: null,
        viewpoint: null,
        color: null,
      });
      addEdge(id, obstacle);
    }
  }

  // Records: one node each, never merged.
  const knownMoments = new Set(detail.moments.moments.map((m) => m.id));
  for (const record of detail.seed_records.records) {
    let parent: string | null = null;
    if (record.moment_id && knownMoments.has(record.moment_id)) {
      if (shownMoments.has(record.moment_id)) parent = nodeId.moment(record.moment_id);
    } else if (reachedSteps.has(record.step_id)) {
      parent = nodeId.step(record.step_id);
    }
    if (!parent) continue;

    const trust = record.provenance.trust_label;
    const viewpoint = viewpointOf(record);
    const marks = [TRUST_EMOJI[trust], viewpoint ? VIEWPOINT_EMOJI[viewpoint] : null].filter(Boolean).join(" ");
    const id = nodeId.record(record.id);
    addNode({
      id,
      kind: "record",
      // Only the emoji on the canvas (keeps ~35 nodes readable); the action text is the detail.
      label: marks,
      detail: record.action.text[lang],
      trust,
      tStart: null,
      viewpoint,
      color: null,
    });
    addEdge(parent, id);
  }

  return { nodes: [...nodes.values()], edges: [...edges.values()] };
}
