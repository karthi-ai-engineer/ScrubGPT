import { act, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { TrustLabel } from "@contracts/contracts";

import i18n from "@/i18n";
import { TRUST_EMOJI, TRUST_LABELS } from "@/lib/trust";

import { TrustBadge } from "./TrustBadge";

const EXPECTED: Record<TrustLabel, { emoji: string; ja: string; en: string }> = {
  ai_detected: { emoji: "🤖", ja: "AI検出", en: "AI-detected" },
  dataset_annotation: { emoji: "📐", ja: "データセット注釈", en: "Dataset annotation" },
  narration_extracted: { emoji: "🎙️", ja: "ナレーション抽出", en: "From narration" },
  operating_surgeon: { emoji: "🩺", ja: "執刀医", en: "Operating surgeon" },
  reviewer: { emoji: "👁️", ja: "レビュアー", en: "Reviewer" },
  expert_validated: { emoji: "✅", ja: "専門家検証済み", en: "Expert-validated" },
  simulated: { emoji: "🧪", ja: "模擬", en: "Simulated" },
};

describe("TrustBadge", () => {
  it("knows all seven contract trust labels, in enum order", () => {
    expect(TRUST_LABELS).toEqual([
      "ai_detected",
      "dataset_annotation",
      "narration_extracted",
      "operating_surgeon",
      "reviewer",
      "expert_validated",
      "simulated",
    ]);
  });

  describe.each(["ja", "en"] as const)("in %s", (lang) => {
    it.each(TRUST_LABELS)("renders %s with its emoji (hidden) and localised name", async (label) => {
      await act(() => i18n.changeLanguage(lang));
      const { container } = render(<TrustBadge label={label} />);
      const expected = EXPECTED[label];

      expect(screen.getByText(expected[lang])).toBeInTheDocument();
      const emoji = container.querySelector('[aria-hidden="true"]');
      expect(emoji).toHaveTextContent(expected.emoji);
      expect(TRUST_EMOJI[label]).toBe(expected.emoji);
      // The accessible text is the name only, not the emoji.
      const badge = container.querySelector(`[data-trust-label="${label}"]`);
      expect(badge).not.toBeNull();
      expect(badge).toHaveAttribute("title", expect.stringContaining(expected[lang]));
    });
  });
});
