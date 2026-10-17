import { useId, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import type { QueueRole } from "@/api/types";
import { TrustBadge } from "@/components/TrustBadge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { readStoredName, ROLE_TRUST, writeStoredName, type Answerer } from "./answerer";
import { ANSWERER_ROLES, forcedQueue, type AnswererRole } from "./fields";

interface AnswererSetupProps {
  initial: Answerer | null;
  defaultRole: AnswererRole;
  /** The list role-play answers from (`?role=`); a surgeon or reviewer has a fixed list. */
  queue: QueueRole;
  onDone: (answerer: Answerer, queue: QueueRole) => void;
}

/** First screen: who is answering (role) and the "confirmed by" name (remembered locally). */
export function AnswererSetup({ initial, defaultRole, queue, onDone }: AnswererSetupProps) {
  const { t } = useTranslation();
  const ids = useId();
  const [role, setRole] = useState<AnswererRole>(initial?.role ?? defaultRole);
  const [name, setName] = useState(() => initial?.name ?? readStoredName());
  const [chosenQueue, setChosenQueue] = useState<QueueRole>(queue);
  const [tried, setTried] = useState(false);
  const fixed = forcedQueue(role);
  const shownQueue = fixed ?? chosenQueue;
  const trimmed = name.trim();

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setTried(true);
    if (!trimmed) return;
    writeStoredName(trimmed);
    onDone({ role, name: trimmed }, shownQueue);
  };

  return (
    <form onSubmit={submit} className="flex flex-col gap-4" aria-labelledby={`${ids}-title`}>
      <div className="flex flex-col gap-1">
        <h2 id={`${ids}-title`} className="m-0 text-lg font-semibold">
          {t("answer.setup.title")}
        </h2>
        <p className="m-0 text-sm text-muted-foreground">{t("answer.setup.intro")}</p>
      </div>

      <fieldset className="m-0 flex flex-col gap-2 border-0 p-0">
        <legend className="mb-1 text-sm font-medium">{t("answer.setup.role")}</legend>
        {ANSWERER_ROLES.map((option) => (
          <label
            key={option}
            className={cn(
              "flex cursor-pointer flex-col gap-1 rounded-lg border border-border bg-card p-3",
              role === option && "border-primary ring-1 ring-primary",
            )}
          >
            <span className="flex items-center gap-2">
              <input
                type="radio"
                name={`${ids}-role`}
                value={option}
                checked={role === option}
                onChange={() => setRole(option)}
                className="size-4 accent-[var(--primary)]"
              />
              <span className="font-medium">{t(`answer.setup.roleOption.${option}`)}</span>
              <TrustBadge label={ROLE_TRUST[option]} className="ml-auto" />
            </span>
            <span className="text-xs text-muted-foreground">{t(`answer.setup.roleHint.${option}`)}</span>
          </label>
        ))}
      </fieldset>

      <fieldset className="m-0 flex flex-col gap-2 border-0 p-0">
        <legend className="mb-1 text-sm font-medium">{t("answer.setup.queue")}</legend>
        <div className="grid grid-cols-2 gap-2">
          {(["operating", "reviewer"] as const).map((option) => {
            const allowed = fixed === null || fixed === option;
            return (
              <label
                key={option}
                className={cn(
                  "flex items-center gap-2 rounded-lg border border-border bg-card p-2.5 text-sm",
                  allowed ? "cursor-pointer" : "cursor-not-allowed opacity-50",
                  shownQueue === option && "border-primary ring-1 ring-primary",
                )}
              >
                <input
                  type="radio"
                  name={`${ids}-queue`}
                  value={option}
                  checked={shownQueue === option}
                  disabled={!allowed}
                  onChange={() => setChosenQueue(option)}
                  className="size-4 accent-[var(--primary)]"
                />
                {t(`answer.setup.queueOption.${option}`)}
              </label>
            );
          })}
        </div>
      </fieldset>

      <div className="flex flex-col gap-1">
        <label htmlFor={`${ids}-name`} className="text-sm font-medium">
          {t("answer.setup.name")}
        </label>
        <input
          id={`${ids}-name`}
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder={t("answer.setup.namePlaceholder")}
          autoComplete="name"
          aria-invalid={tried && !trimmed}
          aria-describedby={`${ids}-name-hint`}
          className="h-10 rounded-md border border-input bg-card px-3 text-base"
        />
        <p
          id={`${ids}-name-hint`}
          className={cn("m-0 text-xs", tried && !trimmed ? "font-medium text-destructive" : "text-muted-foreground")}
        >
          {t("answer.setup.nameRequired")}
        </p>
      </div>

      <Button type="submit" size="lg" disabled={!trimmed}>
        {t("answer.setup.start")}
      </Button>
    </form>
  );
}
