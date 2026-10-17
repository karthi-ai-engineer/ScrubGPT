/**
 * A tidy left-to-right tree for the J8 panel (pure, deterministic): the case in the first column,
 * then steps, moments, and obstacle leaves and records. Each leaf gets its own row and a parent
 * sits at the middle of its children, so labels (drawn to the right of each node) never overlap
 * and a growing graph only pushes rows down: no force simulation, no jitter.
 */
import type { GraphElements } from "./buildGraphElements";

export interface TreeLayoutOptions {
  /** x of depth 1 (the case alone is at x = 0; its label sits under it, so this column is narrow). */
  firstColumn: number;
  /** Horizontal distance between the following depths (model units ≈ px at zoom 1). */
  columnWidth: number;
  /** Vertical distance between leaf rows. */
  rowHeight: number;
}

export const TREE_LAYOUT: TreeLayoutOptions = { firstColumn: 56, columnWidth: 140, rowHeight: 26 };

export interface Point {
  x: number;
  y: number;
}

/** Positions for every node. A node's parent is its first incoming edge; parentless nodes are roots. */
export function treePositions(elements: GraphElements, options: TreeLayoutOptions = TREE_LAYOUT): Record<string, Point> {
  const ids = new Set(elements.nodes.map((n) => n.id));
  const parent = new Map<string, string>();
  for (const edge of elements.edges) {
    if (ids.has(edge.source) && ids.has(edge.target) && !parent.has(edge.target)) parent.set(edge.target, edge.source);
  }
  const children = new Map<string, string[]>();
  for (const node of elements.nodes) {
    const p = parent.get(node.id);
    if (p === undefined) continue;
    const list = children.get(p) ?? [];
    list.push(node.id);
    children.set(p, list);
  }

  const positions: Record<string, Point> = {};
  let row = 0;
  const place = (id: string, depth: number, seen: Set<string>): number => {
    seen.add(id);
    const kids = (children.get(id) ?? []).filter((k) => !seen.has(k));
    let y: number;
    if (kids.length === 0) {
      y = row * options.rowHeight;
      row += 1;
    } else {
      const ys = kids.map((k) => place(k, depth + 1, seen));
      y = ((ys[0] as number) + (ys[ys.length - 1] as number)) / 2;
    }
    positions[id] = { x: depth === 0 ? 0 : options.firstColumn + (depth - 1) * options.columnWidth, y };
    return y;
  };
  const seen = new Set<string>();
  for (const node of elements.nodes) {
    if (!parent.has(node.id) && !seen.has(node.id)) place(node.id, 0, seen);
  }
  return positions;
}
