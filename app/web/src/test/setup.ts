import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach } from "vitest";

import i18n from "@/i18n";

beforeEach(async () => {
  await i18n.changeLanguage("en");
  try {
    window.localStorage.clear();
  } catch {
    // Storage may be stubbed out by a test.
  }
});

afterEach(() => {
  cleanup();
});
