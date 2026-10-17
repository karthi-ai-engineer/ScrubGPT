/**
 * Whether the browser can draw the Cytoscape graph (a 2D canvas). jsdom has no canvas and logs a
 * "not implemented" error when asked, so it is recognised by its user agent first; the panel then
 * shows its node list instead.
 */
export function canvasSupported(): boolean {
  if (typeof document === "undefined" || typeof navigator === "undefined") return false;
  if (/jsdom/i.test(navigator.userAgent)) return false;
  try {
    return document.createElement("canvas").getContext("2d") !== null;
  } catch {
    return false;
  }
}
