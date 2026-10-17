import { useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";
import { useTranslation } from "react-i18next";

import type { Chip, DecisionRecord } from "@contracts/contracts";

import { api, ApiRequestError, isBrainUnavailable, type ClientErrorCode } from "@/api/client";
import { queryKeys } from "@/api/hooks";
import type { DraftResponse } from "@/api/types";
import { TrustBadge } from "@/components/TrustBadge";
import { Button } from "@/components/ui/button";
import { useBilingual, useLang } from "@/i18n/useBilingual";
import { cn } from "@/lib/utils";

import { BrainUnavailableBanner } from "./BrainUnavailableBanner";
import { buildEdits, fieldLabel, isFillable, missingToConfirm, type FieldTexts } from "./fields";

interface ReadbackPanelProps {
  caseId: string;
  result: DraftResponse;
  confirmedBy: string;
  onConfirmed: (record: DecisionRecord) => void;
  onStartOver: () => void;
}

/** A field path's localised label, e.g. "Why not 2". */
function useFieldName() {
  const { t } = useTranslation();
  return (path: string) => {
    const { key, n } = fieldLabel(path);
    const field = t(`answer.field.${key}`);
    return n === null ? field : t("answer.fieldN", { field, n });
  };
}

/**
 * Read-back (plan §8.3): the Brain's `readback`, one chip per `chips[]` entry (never one for a null
 * field, D-056), each `missing_fields[]` entry as an empty fill-in input labelled "not stated", the
 * trust label the record will get, and Confirm, which stays disabled while the cue or the action
 * is still unstated (D-054). The surgeon's words go to the server as `edits`.
 */
export function ReadbackPanel({ caseId, result, confirmedBy, onConfirmed, onStartOver }: ReadbackPanelProps) {
  const { t } = useTranslation();
  const lang = useLang();
  const pick = useBilingual();
  const fieldName = useFieldName();
  const ids = useId();
  const queryClient = useQueryClient();
  const { draft, readback, chips, missing_fields: missing } = result.extract;

  /** Chip edits (field → the corrected text) and filled missing fields (field → text). */
  const [chipEdits, setChipEdits] = useState<FieldTexts>({});
  const [fills, setFills] = useState<FieldTexts>({});
  const [editing, setEditing] = useState<{ field: string; text: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [brainDown, setBrainDown] = useState(false);
  const [error, setError] = useState<ClientErrorCode | null>(null);

  const texts: FieldTexts = { ...fills, ...chipEdits };
  const stillMissing = missingToConfirm(draft, texts);
  const canConfirm = stillMissing.length === 0 && !saving && editing === null;

  const startEdit = (chip: Chip) => setEditing({ field: chip.field, text: chipEdits[chip.field] ?? pick(chip.value) });
  const saveEdit = (chip: Chip) => {
    if (!editing) return;
    const text = editing.text.trim();
    setChipEdits((current) => {
      const next = { ...current };
      // Unchanged or emptied: the chip keeps what the AI read (an edit needs the surgeon's words).
      if (text === "" || text === pick(chip.value).trim()) delete next[chip.field];
      else next[chip.field] = text;
      return next;
    });
    setEditing(null);
  };
  const undoEdit = (field: string) =>
    setChipEdits((current) => {
      const next = { ...current };
      delete next[field];
      return next;
    });

  const confirm = () => {
    if (!canConfirm) return;
    setSaving(true);
    setBrainDown(false);
    setError(null);
    api
      .confirmAnswer({ answer_id: result.answer_id, draft, edits: buildEdits(texts, lang), confirmed_by: confirmedBy })
      .then(
        ({ record }) => {
          void queryClient.invalidateQueries({ queryKey: queryKeys.records(caseId) });
          onConfirmed(record);
        },
        (cause: unknown) => {
          setSaving(false);
          if (isBrainUnavailable(cause)) setBrainDown(true);
          else setError(cause instanceof ApiRequestError ? cause.code : "network");
        },
      );
  };

  return (
    <section aria-labelledby={`${ids}-title`} className="flex flex-col gap-3" data-testid="readback">
      <h3 id={`${ids}-title`} className="m-0 text-base font-semibold">
        {t("answer.readback.title")}
      </h3>
      <p className="m-0 rounded-lg bg-accent p-3 text-sm text-accent-foreground" data-testid="readback-text">
        {pick(readback)}
      </p>

      {chips.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <h4 className="m-0 text-sm font-medium">{t("answer.readback.chips")}</h4>
          <ul className="m-0 flex list-none flex-col gap-1.5 p-0" data-testid="chips">
            {chips.map((chip) => {
              const name = fieldName(chip.field);
              const edited = chipEdits[chip.field];
              const isEditing = editing?.field === chip.field;
              return (
                <li
                  key={chip.field}
                  data-field={chip.field}
                  className={cn("flex flex-col gap-1 rounded-lg border border-border bg-card p-2.5", edited !== undefined && "border-primary")}
                >
                  <span className="flex items-center gap-2 text-xs text-muted-foreground">
                    <span className="font-medium">{name}</span>
                    {edited !== undefined && <span className="rounded bg-accent px-1.5 text-accent-foreground">{t("answer.readback.edited")}</span>}
                  </span>
                  {isEditing ? (
                    <div className="flex flex-col gap-1.5">
                      <textarea
                        aria-label={t("answer.readback.editLabel", { field: name })}
                        value={editing.text}
                        onChange={(event) => setEditing({ field: chip.field, text: event.target.value })}
                        rows={2}
                        className="rounded-md border border-input bg-background p-2 text-sm"
                      />
                      <div className="flex gap-2">
                        <Button size="sm" onClick={() => saveEdit(chip)}>
                          {t("answer.readback.save")}
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setEditing(null)}>
                          {t("answer.readback.cancel")}
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-sm">{edited ?? pick(chip.value)}</span>
                      {chip.editable && (
                        <span className="flex shrink-0 gap-1">
                          {edited !== undefined && (
                            <Button size="sm" variant="ghost" onClick={() => undoEdit(chip.field)}>
                              {t("answer.readback.undo")}
                            </Button>
                          )}
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => startEdit(chip)}
                            aria-label={t("answer.readback.editLabel", { field: name })}
                          >
                            {t("answer.readback.edit")}
                          </Button>
                        </span>
                      )}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {missing.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <h4 className="m-0 text-sm font-medium">{t("answer.readback.missing")}</h4>
          <ul className="m-0 flex list-none flex-col gap-1.5 p-0" data-testid="missing-fields">
            {missing.map((path) => {
              const name = fieldName(path);
              const required = stillMissing.includes(path);
              return (
                <li key={path} data-field={path} className="flex flex-col gap-1">
                  {isFillable(path) ? (
                    <>
                      <label htmlFor={`${ids}-${path}`} className={cn("text-xs", required ? "font-semibold" : "text-muted-foreground")}>
                        {t("answer.readback.fillLabel", { field: name })}
                      </label>
                      <input
                        id={`${ids}-${path}`}
                        value={fills[path] ?? ""}
                        onChange={(event) => setFills((current) => ({ ...current, [path]: event.target.value }))}
                        placeholder={t("answer.readback.notStated")}
                        aria-required={path === "situation_cue.text" || path === "action.text"}
                        className={cn("h-9 rounded-md border bg-card px-2.5 text-sm", required ? "border-primary" : "border-input")}
                      />
                    </>
                  ) : (
                    <p className="m-0 text-xs text-muted-foreground">
                      <span className="font-medium">{name}</span>: {t("answer.readback.cannotFill")}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      <div className="flex flex-col gap-1 rounded-lg border border-border p-2.5 text-xs">
        <span className="flex flex-wrap items-center gap-2">
          <span className="text-muted-foreground">{t("answer.readback.trust")}</span>
          <TrustBadge label={draft.provenance.trust_label} />
        </span>
        <span className="text-muted-foreground">{t("answer.readback.provenance", { name: confirmedBy })}</span>
      </div>

      {brainDown && <BrainUnavailableBanner />}
      {error && (
        <p role="alert" className="m-0 text-sm text-destructive">
          {t("answer.error", { reason: t(`errors.code.${error}`) })}
        </p>
      )}

      {stillMissing.length > 0 && (
        <p className="m-0 text-sm font-medium" id={`${ids}-needs`} data-testid="confirm-hint">
          {t("answer.readback.needs", {
            fields: stillMissing.map(fieldName).join(t("answer.listSeparator")),
          })}
        </p>
      )}
      <div className="flex gap-2">
        <Button
          size="lg"
          className="flex-1"
          disabled={!canConfirm}
          onClick={confirm}
          aria-describedby={stillMissing.length > 0 ? `${ids}-needs` : undefined}
        >
          {saving ? t("answer.readback.confirming") : t("answer.readback.confirm")}
        </Button>
        <Button size="lg" variant="outline" onClick={onStartOver} disabled={saving}>
          {t("answer.readback.startOver")}
        </Button>
      </div>
    </section>
  );
}
