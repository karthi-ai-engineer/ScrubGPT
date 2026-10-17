import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { act } from "react";
import { describe, expect, it, vi } from "vitest";

import i18n from "@/i18n";
import { fixtureSummary, mockFetch } from "@/test/fixtures";
import { renderApp } from "@/test/render";

const casesOk = (url: string) =>
  url === "/api/cases" ? { status: 200, body: { cases: [fixtureSummary] } } : undefined;

describe("Home (J1)", () => {
  it("renders a card for each case from /api/cases", async () => {
    const fetchSpy = mockFetch(casesOk);
    renderApp("/");

    const link = await screen.findByRole("link", { name: fixtureSummary.case.title.en });
    expect(fetchSpy).toHaveBeenCalledWith("/api/cases", expect.anything());
    expect(link).toHaveAttribute("href", "/cases/case-fixture-01");

    const card = link.closest("li");
    if (!card) throw new Error("card not in a list item");
    const c = within(card);

    const poster = c.getByRole("img");
    expect(poster).toHaveAttribute("src", "/media/cases/case-fixture-01/poster.jpg");
    expect(poster).toHaveAttribute("loading", "lazy");
    expect(poster).toHaveAccessibleName(`Poster frame: ${fixtureSummary.case.title.en}`);

    // Facts: source, language, video type, narration, status, duration.
    expect(c.getByText("Synthetic")).toBeInTheDocument();
    expect(c.getByText("Japanese")).toBeInTheDocument();
    expect(c.getByText("Edited video")).toBeInTheDocument();
    expect(c.getByText("Narrated")).toBeInTheDocument();
    expect(c.getByText("Synthetic speech")).toBeInTheDocument();
    expect(c.getByText("Complete")).toBeInTheDocument();
    expect(c.getByText("5:00")).toBeInTheDocument();

    // Counts.
    expect(card.querySelector('[data-count="moments"]')).toHaveTextContent("6");
    expect(card.querySelector('[data-count="operating"]')).toHaveTextContent("8");
    expect(card.querySelector('[data-count="reviewer"]')).toHaveTextContent("4");

    // Trust badges and the data note.
    const badges = c.getByRole("list", { name: "Trust labels" });
    expect(within(badges).getAllByRole("listitem")).toHaveLength(fixtureSummary.trust_labels.length);
    expect(within(badges).getByText("AI-detected")).toBeInTheDocument();
    expect(within(badges).getByText("Simulated")).toBeInTheDocument();
    expect(c.getByText(fixtureSummary.case.data_note.en)).toBeInTheDocument();
  });

  it("shows the content fields in Japanese after switching language", async () => {
    mockFetch(casesOk);
    renderApp("/");
    await screen.findByText(fixtureSummary.case.title.en);

    await act(() => i18n.changeLanguage("ja"));

    expect(screen.getByRole("link", { name: fixtureSummary.case.title.ja })).toBeInTheDocument();
    expect(screen.getByText(fixtureSummary.case.data_note.ja)).toBeInTheDocument();
    expect(screen.getByText("合成データ")).toBeInTheDocument();
    expect(screen.getByText("編集版")).toBeInTheDocument();
    expect(screen.getByText("AI検出")).toBeInTheDocument();
  });

  it("shows an empty state when there are no cases", async () => {
    mockFetch((url) => (url === "/api/cases" ? { status: 200, body: { cases: [] } } : undefined));
    renderApp("/");
    expect(await screen.findByText(/No cases yet/)).toBeInTheDocument();
  });

  it("shows a friendly, localised error with a retry button when the server is unreachable", async () => {
    const user = userEvent.setup();
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
    renderApp("/");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Can't reach the app server");
    expect(alert).not.toHaveTextContent("Failed to fetch");

    await act(() => i18n.changeLanguage("ja"));
    expect(screen.getByRole("alert")).toHaveTextContent("アプリサーバーに接続できません");

    // The server comes back: retry loads the cases.
    fetchSpy.mockRestore();
    mockFetch(casesOk);
    await user.click(screen.getByRole("button", { name: "再試行" }));
    expect(await screen.findByRole("link", { name: fixtureSummary.case.title.ja })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows the error code's localised text for a server error", async () => {
    mockFetch((url) =>
      url === "/api/cases"
        ? {
            status: 503,
            body: { contract_version: "1.0", error: { code: "unavailable", message: "x", retryable: false } },
          }
        : undefined,
    );
    renderApp("/");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Something went wrong");
    expect(alert).toHaveTextContent("The service is unavailable right now.");
  });
});
