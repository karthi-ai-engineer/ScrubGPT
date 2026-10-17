import "i18next";

import type en from "./en.json";

// Typed keys: `t("missing.key")` is a compile error. ja.json must match (unit-tested).
declare module "i18next" {
  interface CustomTypeOptions {
    defaultNS: "translation";
    resources: { translation: typeof en };
  }
}
