import cytoscape from "cytoscape";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import type { TrustLabel } from "@contracts/contracts";

import { NotConfirmedBadge } from "@/components/NotConfirmedBadge";
import { TrustBadge } from "@/components/TrustBadge";
import { TRUST_EMOJI, TRUST_LABELS } from "@/lib/trust";
import { cn } from "@/lib/utils";

import { type GraphElements, VIEWPOINT_EMOJI } from "./buildGraphElements";
import { canvasSupported } from "./canvas";
import { runLayout, STYLE, syncGraph } from "./cytoscapeSync";

interface GraphPanelProps {
  elements: GraphElements;
  /** Called with a moment node's `t_start` when it is selected. */
  onSeek: (seconds: number) => void;
  className?: string;
}

/** J8 graph panel inside the Control Room: renders `buildGraphElements` with Cytoscape.js. */
export function GraphPanel({ elements, onSeek, className }: GraphPanelProps) {
  const { t } = useTranslation();
  const container = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);
  const [drawable] = useState(canvasSupported);
  const [focused, setFocused] = useState<string | null>(null);
  const latestSeek = useRef(onSeek);
  useEffect(() => {
    latestSeek.current = onSeek;
  });
  const latestElements = useRef(elements);
  useEffect(() => {
    latestElements.current = elements;
  });

  useEffect(() => {
    const el = container.current;
    if (!drawable || !el) return;
    const cy = cytoscape({
      container: el,
      style: STYLE,
      elements: [],
      minZoom: 0.3,
      // A small early graph is not blown up; a full one fits at about 0.85.
      maxZoom: 1.3,
      boxSelectionEnabled: false,
      autoungrabify: true,
    });
    cy.on("tap", 'node[kind = "moment"]', (event) => {
      const tStart: unknown = event.target.data("tStart");
      if (typeof tStart === "number") latestSeek.current(tStart);
    });
    // Hover or tap shows a node's full text below the canvas (records draw only their emoji).
    cy.on("tap mouseover", "node", (event) => setFocused(String(event.target.id())));
    cy.on("tap", (event) => {
      if (event.target === cy) setFocused(null);
    });
    cyRef.current = cy;
    if (syncGraph(cy, latestElements.current)) runLayout(cy, latestElements.current);
    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, [drawable]);

  useEffect(() => {
    const cy = cyRef.current;
    if (cy && syncGraph(cy, elements)) runLayout(cy, elements);
  }, [elements]);

  const counts = { steps: 0, moments: 0, records: 0 };
  for (const node of elements.nodes) {
    if (node.kind === "step") counts.steps += 1;
    else if (node.kind === "moment") counts.moments += 1;
    else if (node.kind === "record") counts.records += 1;
  }
  const focusedNode = focused ? elements.nodes.find((n) => n.id === focused) : undefined;
  const present = new Set<TrustLabel>(elements.nodes.flatMap((n) => (n.trust ? [n.trust] : [])));
  const trustInGraph = TRUST_LABELS.filter((label) => present.has(label));

  return (
    <section aria-labelledby="graph-heading" className={cn("flex min-w-0 flex-col gap-2 rounded-xl border border-border bg-card p-3", className)}>
      <div className="flex flex-col gap-0.5">
        <h2 id="graph-heading" className="m-0 text-base font-semibold">
          {t("graph.title")}
        </h2>
        <p className="m-0 text-xs text-muted-foreground">{t("graph.hint")}</p>
        <p className="m-0 text-xs font-medium tabular-nums" data-testid="graph-counts">
          {t("graph.counts", counts)}
        </p>
      </div>

      {drawable && (
        <div
          ref={container}
          role="img"
          aria-label={t("graph.canvasLabel")}
          data-testid="graph-canvas"
          className="h-96 w-full min-w-0 rounded-md border border-border bg-background xl:h-[30rem]"
        />
      )}
      {drawable && (
        <p className="m-0 flex min-h-6 flex-wrap items-center gap-1.5 text-xs" aria-live="polite" data-testid="graph-detail">
          {focusedNode ? (
            <>
              <span className="text-muted-foreground">{t(`graph.kind.${focusedNode.kind}`)}</span>
              {focusedNode.viewpoint && (
                <span className="text-muted-foreground">
                  {VIEWPOINT_EMOJI[focusedNode.viewpoint]} {t(`graph.${focusedNode.viewpoint}`)}
                </span>
              )}
              <span className="font-medium">{focusedNode.detail}</span>
              {focusedNode.trust && <TrustBadge label={focusedNode.trust} />}
              {focusedNode.unconfirmed && <NotConfirmedBadge />}
            </>
          ) : (
            <span className="text-muted-foreground">{t("graph.detailHint")}</span>
          )}
        </p>
      )}

      {/* The same nodes as text: for screen readers, and the panel itself without a canvas. */}
      <ul aria-label={t("graph.listLabel")} className={cn("m-0 list-none p-0 text-xs", drawable ? "sr-only" : "flex max-h-80 flex-col gap-1 overflow-y-auto")}>
        {elements.nodes.map((node) => (
          <li key={node.id} data-node-id={node.id} data-node-kind={node.kind} className="flex flex-wrap items-center gap-1.5">
            <span className="text-muted-foreground">{t(`graph.kind.${node.kind}`)}</span>
            {node.viewpoint && <span aria-hidden="true">{VIEWPOINT_EMOJI[node.viewpoint]}</span>}
            {node.viewpoint && <span className="text-muted-foreground">{t(`graph.${node.viewpoint}`)}</span>}
            <span>{node.detail}</span>
            {node.trust && <TrustBadge label={node.trust} />}
            {node.unconfirmed && <NotConfirmedBadge />}
          </li>
        ))}
      </ul>

      <dl aria-label={t("graph.legend")} className="m-0 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
        <div className="flex items-center gap-1">
          <dt aria-hidden="true">{VIEWPOINT_EMOJI.operating}</dt>
          <dd className="m-0">{t("graph.operating")}</dd>
        </div>
        <div className="flex items-center gap-1">
          <dt aria-hidden="true">{VIEWPOINT_EMOJI.reviewer}</dt>
          <dd className="m-0">{t("graph.reviewer")}</dd>
        </div>
        {trustInGraph.map((label) => (
          <div key={label} className="flex items-center gap-1">
            <dt aria-hidden="true">{TRUST_EMOJI[label]}</dt>
            <dd className="m-0">{t(`trust.${label}`)}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
