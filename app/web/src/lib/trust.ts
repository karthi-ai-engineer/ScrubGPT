import type { TrustLabel } from "@contracts/contracts";

/**
 * Trust labels in contract enum order (plan §4.1). The emoji are display-only.
 * `Record<TrustLabel, …>` makes the compiler flag a label added to the contract.
 */
export const TRUST_EMOJI: Readonly<Record<TrustLabel, string>> = {
  ai_detected: "🤖",
  dataset_annotation: "📐",
  narration_extracted: "🎙️",
  operating_surgeon: "🩺",
  reviewer: "👁️",
  expert_validated: "✅",
  simulated: "🧪",
};

export const TRUST_LABELS = Object.keys(TRUST_EMOJI) as TrustLabel[];
