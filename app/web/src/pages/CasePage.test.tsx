import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { fixtureDetail, mockFetch } from "@/test/fixtures";
import { renderApp } from "@/test/render";

const routes = (url: string) => {
  if (url === "/api/cases/case-fixture-01") return { status: 200, body: fixtureDetail };
  return undefined; // everything else (incl. the reference) → 404 not_found
};

describe("Case page", () => {
  it("shows the title, the player and the moments; clicking a moment seeks to its start", async () => {
    const user = userEvent.setup();
    mockFetch(routes);
    const { container } = renderApp("/cases/case-fixture-01");

    expect(await screen.findByRole("heading", { level: 1, name: fixtureDetail.case.title.en })).toBeInTheDocument();

    const video = container.querySelector("video");
    expect(video).toHaveAttribute("src", "/media/cases/case-fixture-01/video.mp4");
    expect(video).toHaveAttribute("poster", "/media/cases/case-fixture-01/poster.jpg");

    const list = screen.getByRole("heading", { name: "Flagged moments" }).closest("section");
    if (!list) throw new Error("no moments section");
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(fixtureDetail.moments.moments.length);

    const first = fixtureDetail.moments.moments[0];
    const firstItem = within(items[0]);
    expect(firstItem.getByText(first.title.en)).toBeInTheDocument();
    expect(firstItem.getByText("0:58–1:18")).toBeInTheDocument();
    expect(firstItem.getByText("Event")).toBeInTheDocument();
    expect(firstItem.getByText("AI-detected")).toBeInTheDocument();
    // Reference not available (404): the raw step id is shown.
    expect(firstItem.getByText(/rarp\.p04\.s02/)).toBeInTheDocument();

    const second = fixtureDetail.moments.moments[1];
    await user.click(within(items[1]).getByRole("button"));
    expect(video?.currentTime).toBe(second.t_start);
  });

  it("shows step names from the Procedure Reference when it loads", async () => {
    mockFetch((url) => {
      if (url === "/api/references/rarp") {
        return {
          status: 200,
          body: {
            contract_version: "1.0",
            id: "rarp",
            name: { ja: "RARP", en: "RARP" },
            phases: [
              {
                id: "rarp.p04",
                name: { ja: "フェーズ", en: "Phase" },
                order: 4,
                typical_duration_s: { p25: 1, p50: 2, p75: 3 },
                steps: [
                  {
                    id: "rarp.p04.s02",
                    name: { ja: "DVCの処理", en: "DVC control" },
                    order: 2,
                    typical_duration_s: { p25: 1, p50: 2, p75: 3 },
                    checkpoints: [],
                  },
                ],
              },
            ],
            obstacle_taxonomy: [],
          },
        };
      }
      return routes(url);
    });
    renderApp("/cases/case-fixture-01");
    expect(await screen.findByText("Step: DVC control")).toBeInTheDocument();
  });

  it("shows a localised 'case not found' with a link home for an unknown id", async () => {
    mockFetch(routes);
    renderApp("/cases/nope");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Case not found");
    expect(alert).toHaveTextContent("nope");
    expect(within(alert).getByRole("link", { name: "Back to home" })).toHaveAttribute("href", "/");
  });
});
