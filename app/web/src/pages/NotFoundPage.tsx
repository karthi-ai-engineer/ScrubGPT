import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { buttonVariants } from "@/components/ui/button";

export function NotFoundPage() {
  const { t } = useTranslation();
  return (
    <div className="mx-auto my-8 flex max-w-xl flex-col items-start gap-3 rounded-xl border border-border bg-card p-6">
      <h1 className="m-0 text-xl font-semibold">{t("errors.pageNotFound.title")}</h1>
      <p className="m-0 text-muted-foreground">{t("errors.pageNotFound.body")}</p>
      <Link to="/" className={buttonVariants()}>
        {t("status.backHome")}
      </Link>
    </div>
  );
}
