/**
 * Lookups into the Procedure Reference (plan §4.2b): bilingual step, checkpoint and obstacle
 * names, and the phase of a step. Every lookup tolerates a missing Reference (the caller then
 * shows the raw id).
 */
import type { Bilingual, Checkpoint, ObstacleLeaf, ProcedureReference } from "@contracts/contracts";

export interface ReferenceLookup {
  stepName: (stepId: string) => Bilingual | undefined;
  checkpoint: (checkpointId: string) => Checkpoint | undefined;
  obstacle: (leafId: string) => ObstacleLeaf | undefined;
  /** The phase's `order` (1-based) from the Reference, else the `pNN` number of the id. */
  phaseOrder: (stepId: string) => number | null;
}

/** The procedure of a step id such as `rarp.p03.s01` (plan §4.1 id format): `rarp`. */
export function procedureOf(stepId: string | undefined): string | null {
  if (!stepId) return null;
  return stepId.split(".")[0] || null;
}

/** The phase id of a step id: `rarp.p03.s01` → `rarp.p03`. */
export function phaseIdOf(stepId: string): string {
  return stepId.split(".").slice(0, 2).join(".");
}

export function buildReferenceLookup(reference: ProcedureReference | undefined): ReferenceLookup {
  const steps = new Map<string, Bilingual>();
  const checkpoints = new Map<string, Checkpoint>();
  const phases = new Map<string, number>();
  const leaves = new Map<string, ObstacleLeaf>();
  for (const phase of reference?.phases ?? []) {
    phases.set(phase.id, phase.order);
    for (const step of phase.steps) {
      steps.set(step.id, step.name);
      for (const checkpoint of step.checkpoints) checkpoints.set(checkpoint.id, checkpoint);
    }
  }
  for (const family of reference?.obstacle_taxonomy ?? []) {
    for (const leaf of family.leaves) leaves.set(leaf.id, leaf);
  }
  return {
    stepName: (id) => steps.get(id),
    checkpoint: (id) => checkpoints.get(id),
    obstacle: (id) => leaves.get(id),
    phaseOrder: (stepId) => {
      const known = phases.get(phaseIdOf(stepId));
      if (known !== undefined) return known;
      const match = /\.p(\d+)(?:\.|$)/.exec(stepId);
      return match ? Number(match[1]) : null;
    },
  };
}

/**
 * Calm, distinguishable phase colours (one per phase, cycling). Only reached step segments are
 * coloured; unreached ones stay neutral so the bar gives nothing away.
 */
export const PHASE_COLORS = [
  "#2f6f8f",
  "#3d8a6e",
  "#7a6bb0",
  "#b0763c",
  "#4f7fbf",
  "#8a5a83",
  "#5f8f3d",
  "#b05a5a",
  "#3d7f8a",
  "#8f7a2f",
  "#5a6fb0",
  "#6f8a5a",
  "#a0603f",
] as const;

export function phaseColor(order: number | null): string {
  if (order === null || order < 1) return "#64748b";
  return PHASE_COLORS[(order - 1) % PHASE_COLORS.length] as string;
}
