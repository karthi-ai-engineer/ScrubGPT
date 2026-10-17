import { useTranslation } from "react-i18next";

import { ApiRequestError } from "@/api/client";
import { Button } from "@/components/ui/button";

export function LoadingState() {
  const { t } = useTranslation();
  return (
    <p role="status" className="py-12 text-center text-muted-foreground">
      {t("status.loading")}
    </p>
  );
}

/** A friendly, localised error with a retry button. Never shows the raw server text. */
export function ErrorState({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  const { t } = useTranslation();
  const code = error instanceof ApiRequestError ? error.code : "network";
  const unreachable = code === "network";
  return (
    <div
      role="alert"
      className="mx-auto my-8 flex max-w-xl flex-col items-start gap-3 rounded-xl border border-border bg-card p-6"
    >
      <h2 className="m-0 text-lg font-semibold">
        {unreachable ? t("errors.network.title") : t("errors.generic.title")}
      </h2>
      <p className="m-0 text-muted-foreground">
        {unreachable ? t("errors.network.body") : t(`errors.code.${code}`)}
      </p>
      {onRetry && <Button onClick={onRetry}>{t("status.retry")}</Button>}
    </div>
  );
}
