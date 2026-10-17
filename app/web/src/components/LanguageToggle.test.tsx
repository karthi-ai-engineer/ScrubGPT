import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { LANG_STORAGE_KEY } from "@/i18n";
import { fixtureSummary, mockFetch } from "@/test/fixtures";
import { renderApp } from "@/test/render";

describe("JA | EN toggle (J15)", () => {
  beforeEach(() => {
    mockFetch((url) => (url === "/api/cases" ? { status: 200, body: { cases: [fixtureSummary] } } : undefined));
  });

  it("switches every UI string and content field instantly, sets <html lang> and remembers the choice", async () => {
    const user = userEvent.setup();
    renderApp("/");

    // English first (setup resets to en).
    expect(screen.getByText("Surgical Knowledge System")).toBeInTheDocument();
    expect(screen.getByText("Education and reference only — not clinical advice.")).toBeInTheDocument();
    expect(await screen.findByText(fixtureSummary.case.title.en)).toBeInTheDocument();

    const toggle = screen.getByRole("group", { name: "Display language" });
    const jaButton = within(toggle).getByRole("button", { name: "日本語 (Japanese)" });
    expect(jaButton).toHaveAttribute("aria-pressed", "false");

    await user.click(jaButton);

    // No reload, no refetch needed: the same render tree is now Japanese.
    expect(screen.getByText("手術知識システム")).toBeInTheDocument();
    expect(screen.getByText("教育・参考用です。臨床上の助言ではありません。")).toBeInTheDocument();
    expect(screen.getByText("デモデータ")).toBeInTheDocument();
    expect(screen.getByText(fixtureSummary.case.title.ja)).toBeInTheDocument();
    expect(screen.queryByText(fixtureSummary.case.title.en)).not.toBeInTheDocument();
    expect(document.documentElement.lang).toBe("ja");
    expect(window.localStorage.getItem(LANG_STORAGE_KEY)).toBe("ja");

    const toggleJa = screen.getByRole("group", { name: "表示言語" });
    expect(within(toggleJa).getByRole("button", { name: "日本語" })).toHaveAttribute("aria-pressed", "true");

    await user.click(within(toggleJa).getByRole("button", { name: "English（英語）" }));
    expect(screen.getByText("Surgical Knowledge System")).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("en");
    expect(window.localStorage.getItem(LANG_STORAGE_KEY)).toBe("en");
  });

  it("always shows the disclaimer and the demo-data badge", () => {
    renderApp("/no-such-page");
    expect(screen.getByRole("region", { name: "Notice" })).toHaveTextContent(
      "Education and reference only — not clinical advice.",
    );
    expect(screen.getByText("Demo data")).toBeInTheDocument();
  });
});
