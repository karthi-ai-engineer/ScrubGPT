/**
 * Browser stand-ins for unit tests (jsdom has neither `EventSource` nor `MediaRecorder`):
 * a hand-driven `EventSource`, and a fake microphone (`getUserMedia` + `MediaRecorder`).
 */
import { vi } from "vitest";

/** A stand-in for the browser's EventSource that the test drives by hand. */
export class FakeEventSource {
  static instances: FakeEventSource[] = [];
  readonly url: string;
  readyState = 0;
  closed = false;
  onopen: ((e: Event) => void) | null = null;
  onerror: ((e: Event) => void) | null = null;
  private listeners = new Map<string, Set<(e: MessageEvent<string>) => void>>();

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }
  addEventListener(name: string, fn: (e: MessageEvent<string>) => void) {
    if (!this.listeners.has(name)) this.listeners.set(name, new Set());
    this.listeners.get(name)?.add(fn);
  }
  removeEventListener(name: string, fn: (e: MessageEvent<string>) => void) {
    this.listeners.get(name)?.delete(fn);
  }
  listenerCount(name: string) {
    return this.listeners.get(name)?.size ?? 0;
  }
  close() {
    this.closed = true;
    this.readyState = 2;
  }
  open() {
    this.readyState = 1;
    this.onopen?.(new Event("open"));
  }
  emit(name: string, data: unknown) {
    const event = new MessageEvent(name, { data: typeof data === "string" ? data : JSON.stringify(data) });
    for (const fn of this.listeners.get(name) ?? []) fn(event);
  }

  static install() {
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
  }
  static live() {
    return FakeEventSource.instances.filter((s) => !s.closed);
  }
}

/** A fake `MediaRecorder`: `stop()` delivers one chunk of synthetic bytes, then `onstop`. */
export class FakeMediaRecorder {
  static instances: FakeMediaRecorder[] = [];
  static supported = new Set<string>(["audio/webm;codecs=opus", "audio/webm"]);
  static isTypeSupported(type: string) {
    return FakeMediaRecorder.supported.has(type);
  }
  readonly mimeType: string;
  state: "inactive" | "recording" = "inactive";
  ondataavailable: ((e: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;

  constructor(_stream: unknown, options?: { mimeType?: string }) {
    this.mimeType = options?.mimeType ?? "";
    FakeMediaRecorder.instances.push(this);
  }
  start() {
    this.state = "recording";
  }
  stop() {
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob([new Uint8Array([1, 2, 3, 4])], { type: this.mimeType }) });
    this.onstop?.();
  }
}

export interface FakeMic {
  getUserMedia: ReturnType<typeof vi.fn>;
  stopTrack: ReturnType<typeof vi.fn>;
}

/**
 * Installs a microphone: `getUserMedia` resolves with a fake stream (or rejects with `deny`, a
 * DOMException name such as `NotAllowedError`), and `MediaRecorder` is the fake above.
 */
export function installFakeMic(options: { deny?: string; supported?: string[] } = {}): FakeMic {
  FakeMediaRecorder.instances = [];
  FakeMediaRecorder.supported = new Set(options.supported ?? ["audio/webm;codecs=opus", "audio/webm"]);
  const stopTrack = vi.fn();
  const getUserMedia = vi.fn(async () => {
    if (options.deny) throw new DOMException("denied", options.deny);
    return { getTracks: () => [{ stop: stopTrack }] };
  });
  vi.stubGlobal("MediaRecorder", FakeMediaRecorder);
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia } });
  return { getUserMedia, stopTrack };
}

/** Removes the microphone again (no `mediaDevices`, no `MediaRecorder`). */
export function removeFakeMic() {
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: undefined });
}
