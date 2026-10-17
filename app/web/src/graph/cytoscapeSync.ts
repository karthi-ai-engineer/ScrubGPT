/** Cytoscape glue for the J8 panel (kept apart from the component so it can be unit-tested). */
import type cytoscape from "cytoscape";

import type { GraphElements, GraphNode } from "./buildGraphElements";
import { treePositions } from "./treeLayout";

const FONT =
  'system-ui, -apple-system, "Segoe UI", "Hiragino Sans", "Hiragino Kaku Gothic ProN", "Noto Sans JP", "Yu Gothic UI", "Meiryo", sans-serif';

/** Label size in model units; at the panel's fitted zoom (≈ 0.9 at 1440 px with the full fixture graph) it is ≥ 11 px. */
export const LABEL_FONT_SIZE = 13;

/** Calm, clinical styling: no decorative animation; colour carries the node kind. */
export const STYLE: cytoscape.StylesheetJson = [
  {
    selector: "node",
    style: {
      label: "data(label)",
      "font-family": FONT,
      "font-size": LABEL_FONT_SIZE,
      color: "#0f1b2a",
      // One line per label, cut with an ellipsis to fit its column (wrapping overlapped the rows,
      // and Japanese has no spaces to wrap at); the full text shows on hover/tap.
      "text-wrap": "ellipsis",
      "text-max-width": "112px",
      "text-halign": "right",
      "text-valign": "center",
      "text-margin-x": 5,
      // An opaque label background: edges pass under labels instead of through the text.
      "text-background-color": "#f6f8fa",
      "text-background-opacity": 1,
      "text-background-padding": "1px",
      // Labels stay drawn at any zoom the panel fits to (no hiding of small text).
      "min-zoomed-font-size": 0,
      width: 14,
      height: 14,
      "border-width": 1.5,
      "border-color": "#0f1b2a",
      "background-color": "#cfd8e1",
    },
  },
  {
    selector: 'node[kind = "case"]',
    style: {
      shape: "round-rectangle",
      width: 18,
      height: 18,
      "background-color": "#0f1b2a",
      "font-weight": "bold",
      // The case sits alone in a narrow first column: its label goes under it.
      "text-halign": "center",
      "text-valign": "bottom",
      "text-margin-x": 0,
      "text-margin-y": 4,
      "text-max-width": "84px",
    },
  },
  { selector: 'node[kind = "step"]', style: { shape: "ellipse", "background-color": "data(color)" } },
  {
    selector: 'node[kind = "moment"]',
    style: { shape: "diamond", width: 16, height: 16, "background-color": "#f5c46a", "border-color": "#8a5a00" },
  },
  { selector: 'node[kind = "obstacle"]', style: { shape: "hexagon", "background-color": "#e7edf2", "border-color": "#4a5a6b" } },
  { selector: 'node[kind = "record"]', style: { shape: "round-rectangle", width: 14, height: 11, "background-color": "#dff1f3" } },
  { selector: 'node[viewpoint = "operating"]', style: { "border-color": "#0b5f6e", "border-width": 2.5 } },
  { selector: 'node[viewpoint = "reviewer"]', style: { "border-color": "#6b4fa0", "border-width": 2.5, "border-style": "dashed" } },
  { selector: "node:selected", style: { "overlay-color": "#0b5f6e", "overlay-opacity": 0.15, "overlay-padding": 4 } },
  {
    selector: "edge",
    style: {
      width: 1.25,
      "line-color": "#9fb0c0",
      "curve-style": "taxi",
      "taxi-direction": "rightward",
      // Turn just before the child column, after the parent's label (tree brackets).
      "taxi-turn": "-14px",
      "target-arrow-shape": "none",
    },
  },
];

function toNodeData(node: GraphNode): Record<string, unknown> {
  return {
    id: node.id,
    label: node.label,
    kind: node.kind,
    trust: node.trust,
    tStart: node.tStart,
    viewpoint: node.viewpoint,
    color: node.color ?? "#cfd8e1",
  };
}

/**
 * Brings the Cytoscape graph in line with `elements`: removes what is no longer revealed (a
 * backwards seek), updates labels (language toggle) and adds new elements. Returns whether the
 * set of nodes changed (only then is the layout re-run; a language switch keeps every position).
 */
export function syncGraph(cy: cytoscape.Core, elements: GraphElements): boolean {
  const wanted = new Set<string>([...elements.nodes.map((n) => n.id), ...elements.edges.map((e) => e.id)]);
  let changed = false;
  cy.batch(() => {
    cy.elements().forEach((el) => {
      if (!wanted.has(el.id()) && el.inside()) {
        if (el.isNode()) changed = true;
        el.remove();
      }
    });
    for (const node of elements.nodes) {
      const existing = cy.getElementById(node.id);
      if (existing.nonempty()) {
        existing.data(toNodeData(node));
        continue;
      }
      cy.add({ group: "nodes", data: toNodeData(node), position: { x: 0, y: 0 } });
      changed = true;
    }
    for (const edge of elements.edges) {
      if (cy.getElementById(edge.id).empty()) {
        cy.add({ group: "edges", data: { id: edge.id, source: edge.source, target: edge.target } });
      }
    }
  });
  return changed;
}

/** Places the nodes as a left-to-right tree (`treePositions`) and fits the panel. No animation. */
export function runLayout(cy: cytoscape.Core, elements: GraphElements): void {
  const positions = treePositions(elements);
  cy.layout({ name: "preset", positions, fit: true, padding: 10, animate: false }).run();
  // The on-screen label size after fitting, for checks (e.g. `data-label-px="11.5"`).
  const container = cy.container?.();
  if (container) container.dataset.labelPx = (LABEL_FONT_SIZE * cy.zoom()).toFixed(1);
}
