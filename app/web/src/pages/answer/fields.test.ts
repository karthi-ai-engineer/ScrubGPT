import { describe, expect, it } from "vitest";

import en from "@/i18n/en.json";
import ja from "@/i18n/ja.json";
import { draftFor } from "@/test/answerFixtures";

import { buildEdits, canAnswer, fieldLabel, forcedQueue, isFillable, missingToConfirm } from "./fields";

describe("canAnswer (D-066: who may answer which question)", () => {
  it.each([
    ["operating_surgeon", "case-fixture-01.m01.q1", true],
    ["operating_surgeon", "case-fixture-01.m01.r1", false],
    ["reviewer", "case-fixture-01.m01.r1", true],
    ["reviewer", "case-fixture-01.m01.q1", false],
    ["dev_team_simulated", "case-fixture-01.m01.q1", true],
    ["dev_team_simulated", "case-fixture-01.m01.r2", true],
    ["expert", "case-fixture-01.m01.r2", true],
    ["ai", "case-fixture-01.m01.q1", false],
    ["narrator", "case-fixture-01.m01.q1", false],
    ["dataset", "case-fixture-01.m01.r1", false],
  ] as const)("%s → %s: %s", (role, question, allowed) => {
    expect(canAnswer(role, question)).toBe(allowed);
  });

  it("fixes the list for a surgeon or a reviewer; role-play may use either", () => {
    expect(forcedQueue("operating_surgeon")).toBe("operating");
    expect(forcedQueue("reviewer")).toBe("reviewer");
    expect(forcedQueue("dev_team_simulated")).toBeNull();
  });
});

describe("field labels", () => {
  it.each([
    ["situation_cue.text", "situation_cue", null],
    ["action.text", "action", null],
    ["reason", "reason", null],
    ["alternatives", "alternatives", null],
    ["alternatives[0].option", "alternative_option", null],
    ["alternatives[0].why_not", "why_not", null],
    ["alternatives[1].why_not", "why_not", 2],
    ["immediate_result", "immediate_result", null],
    ["anticipation", "anticipation", null],
    ["context.preop_plan", "preop_plan", null],
    ["context.patient_factors[0]", "patient_factors", null],
    ["context.patient_factors[2]", "patient_factors", 3],
    ["obstacle", "obstacle", null],
    ["delayed_outcome.text", "other", null],
  ] as const)("%s → %s", (path, key, n) => {
    expect(fieldLabel(path)).toEqual({ key, n });
  });

  it("names the chip fields in both languages", () => {
    expect(en.answer.field).toMatchObject({
      situation_cue: "Situation cue",
      action: "Action",
      reason: "Reason",
      alternatives: "Alternatives",
      why_not: "Why not",
      immediate_result: "Immediate result",
      anticipation: "Anticipation",
      preop_plan: "Pre-op plan",
      patient_factors: "Patient factors",
    });
    expect(ja.answer.field).toMatchObject({
      situation_cue: "状況の手がかり",
      action: "対応",
      reason: "理由",
      alternatives: "他の選択肢",
      why_not: "選ばなかった理由",
      immediate_result: "直後の結果",
      anticipation: "予測",
      preop_plan: "術前計画",
      patient_factors: "患者要因",
    });
    expect(en.answer.readback.notStated).toBe("not stated");
    expect(ja.answer.readback.notStated).toBe("未回答");
    expect(en.record.notConfirmed).toBe("Not confirmed");
    expect(ja.record.notConfirmed).toBe("未確認");
  });

  it("only text fields the server can store as edits are fill-in inputs", () => {
    for (const path of ["situation_cue.text", "action.text", "reason", "alternatives[0].why_not", "alternatives[1].option", "context.preop_plan"]) {
      expect(isFillable(path), path).toBe(true);
    }
    for (const path of ["obstacle", "alternatives", "context.patient_factors", "situation_cue", "delayed_outcome.text"]) {
      expect(isFillable(path), path).toBe(false);
    }
  });
});

describe("Confirm needs the cue and the action (D-054)", () => {
  it("lists the unstated required fields until the surgeon fills them", () => {
    const draft = draftFor("case-fixture-01.m01.q1", { only: ["reason"] });
    expect(missingToConfirm(draft, {})).toEqual(["situation_cue.text", "action.text"]);
    expect(missingToConfirm(draft, { "situation_cue.text": "  " })).toEqual(["situation_cue.text", "action.text"]);
    expect(missingToConfirm(draft, { "situation_cue.text": "Oozing" })).toEqual(["action.text"]);
    expect(missingToConfirm(draft, { "situation_cue.text": "Oozing", "action.text": "Pressure" })).toEqual([]);
    expect(missingToConfirm(draftFor("case-fixture-01.m01.q1"), {})).toEqual([]);
  });

  it("sends only non-blank texts, trimmed, in the language typed", () => {
    expect(buildEdits({ reason: "  Because  ", "action.text": "   ", "situation_cue.text": "出血" }, "ja")).toEqual([
      { field: "reason", text: "Because", lang: "ja" },
      { field: "situation_cue.text", text: "出血", lang: "ja" },
    ]);
  });
});
