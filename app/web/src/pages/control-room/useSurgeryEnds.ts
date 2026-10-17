import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "@/api/client";
import { useServerEvent } from "@/api/events";
import type { CaseEndedEvent } from "@/api/types";
import type { VideoClock } from "@/replay/clock";
import { useReplayEnd } from "@/replay/hooks";

export interface SurgeryEnds {
  /** The `case.ended` payload for this case once the replay ended; `null` before. */
  ended: CaseEndedEvent | null;
  /** The `replay-ended` POST failed. */
  failed: boolean;
  retry: () => void;
}

/**
 * "Surgery ends" (plan §8.2): at the end of the video, POST `replay-ended` once per play-through;
 * the server answers with `case.ended` over SSE, which shows the banner. The POST's reply (the same
 * payload) stands in only while the event stream is not connected. Going back before the end
 * starts a new play-through and hides the banner.
 */
export function useSurgeryEnds(caseId: string, clock: VideoClock, durationHint: number): SurgeryEnds {
  const [ended, setEnded] = useState<CaseEndedEvent | null>(null);
  const [failed, setFailed] = useState(false);
  const playThrough = useRef(0);

  const connected = useServerEvent("case.ended", (data) => {
    if (data.case_id === caseId) setEnded(data);
  });
  const connectedNow = useRef(connected);
  useEffect(() => {
    connectedNow.current = connected;
  });

  const notify = useCallback(() => {
    const run = playThrough.current;
    setFailed(false);
    api.replayEnded(caseId).then(
      (payload) => {
        if (run === playThrough.current && !connectedNow.current && payload.case_id === caseId) setEnded(payload);
      },
      () => {
        if (run === playThrough.current) setFailed(true);
      },
    );
  }, [caseId]);

  useReplayEnd(clock, durationHint, {
    onEnd: notify,
    onRestart: () => {
      playThrough.current += 1;
      setEnded(null);
      setFailed(false);
    },
  });

  return { ended, failed, retry: notify };
}
