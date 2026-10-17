/**
 * J8 graph panel: "Selecting a moment node seeks the video" (brief criterion 8; graph hint
 * "Select a moment node to jump the video"; plan §8.2 the video is the master clock).
 *
 * jsdom has no canvas, so the panel normally shows only its node list. Here the real Cytoscape.js
 * runs **headless** (no rendering, same graph, same events) and the panel is told a canvas exists;
 * a tap on a moment node is then emitted on the real Cytoscape element.
 */
import { act, waitFor } from "@testing-library/react";
import type cytoscapeType from "cytoscape";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fixture } from "./harness";
import {
  installEventSource,
  installReplayMedia,
  mockApi,
  playTo,
  renderControlRoom,
  video,
} from "./replay-harness";

const created = vi.hoisted(() => ({ instances: [] as cytoscapeType.Core[] }));

vi.mock("@/graph/canvas", () => ({ canvasSupported: () => true }));
vi.mock("cytoscape", async (importOriginal) => {
  const mod = await importOriginal<{ default: typeof cytoscapeType }>();
  const real = mod.default;
  const headless = ((options: cytoscapeType.CytoscapeOptions = {}) => {
    const cy = real({ ...options, container: undefined, headless: true, styleEnabled: true });
    created.instances.push(cy);
    return cy;
  }) as unknown as typeof cytoscapeType;
  Object.assign(headless, real);
  return { ...mod, default: headless };
});

const moments = fixture.moments.moments;

let restoreMedia: () => void;
beforeEach(() => {
  created.instances = [];
  restoreMedia = installReplayMedia();
  installEventSource();
});
afterEach(() => restoreMedia());

function cy(): cytoscapeType.Core {
  const live = created.instances.filter((c) => !c.destroyed());
  expect(live.length).toBeGreaterThan(0);
  return live[live.length - 1]!;
}

/** The graph node that shows `text` in any of its data fields. */
function nodeShowing(text: string): cytoscapeType.NodeSingular {
  const hits = cy()
    .nodes()
    .filter((n) => JSON.stringify(n.data()).includes(text));
  expect(hits.length, `a node showing "${text}"`).toBe(1);
  return hits[0]!;
}

describe("J8 graph panel selection", () => {
  it("criterion 8: selecting a moment node seeks the video to the moment's t_start", async () => {
    mockApi();
    await renderControlRoom();
    await playTo(130);
    const shown = moments.filter((m) => m.t_start <= 130).sort((a, b) => b.t_start - a.t_start);
    await waitFor(() => expect(cy().nodes().length).toBeGreaterThan(shown.length));
    // Newest first: each seek hides the later moments again (criterion 4).
    for (const m of shown) {
      await waitFor(() => nodeShowing(m.title.en));
      await act(async () => {
        nodeShowing(m.title.en).emit("tap");
        await new Promise((r) => setTimeout(r, 5));
      });
      await waitFor(() => expect(video().currentTime).toBe(m.t_start));
    }
  });

  it("criterion 8: selecting a step or obstacle node does not seek", async () => {
    mockApi();
    await renderControlRoom();
    await playTo(130);
    const m01 = moments[0]!;
    const step = fixture.reference.phases.flatMap((p) => p.steps).find((x) => x.id === m01.step_id)!;
    const leaf = fixture.reference.obstacle_taxonomy.flatMap((f) => f.leaves).find((l) => l.id === m01.draft_obstacle)!;
    // Canvas labels may be shortened; a prefix identifies the node.
    for (const text of [step.name.en.slice(0, 18), leaf.name.en.slice(0, 18)]) {
      await waitFor(() => nodeShowing(text));
      await act(async () => {
        nodeShowing(text).emit("tap");
        await new Promise((r) => setTimeout(r, 5));
      });
      expect(video().currentTime, text).toBe(130);
    }
  });
});
