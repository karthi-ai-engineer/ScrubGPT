import { useCallback, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router";

import type { StepTrack } from "@contracts/contracts";

import { ApiRequestError } from "@/api/client";
import { useCase, useReference } from "@/api/hooks";
import type { CaseDetail } from "@/api/types";
import { ErrorState, LoadingState } from "@/components/QueryStatus";
import { TrustBadgeList } from "@/components/TrustBadge";
import { Button } from "@/components/ui/button";
import { VideoPlayer, type VideoPlayerHandle } from "@/components/VideoPlayer";
import { buildGraphElements } from "@/graph/buildGraphElements";
import { GraphPanel } from "@/graph/GraphPanel";
import { useBilingual, useLang } from "@/i18n/useBilingual";
import { buildReferenceLookup, procedureOf } from "@/lib/reference";
import { useMediaDuration, useReplayState, useVideoClock } from "@/replay/hooks";
import { availableTracks, buildReplayIndex, selectTrack } from "@/replay/sync";
import { CaseNotFound } from "@/pages/CasePage";

import { AlertsPanel } from "./AlertsPanel";
import { EventStrip } from "./EventStrip";
import { StepBar } from "./StepBar";
import { SurgeryEndedPanel } from "./SurgeryEndedPanel";
import { TranscriptTicker } from "./TranscriptTicker";
import { useSurgeryEnds } from "./useSurgeryEnds";

/** J2: the Control Room, a "live" replay of a recorded case (plan §2.10, §8.2). */
export function ControlRoomPage() {
  const { caseId = "" } = useParams();
  const query = useCase(caseId);

  if (query.isPending) return <LoadingState />;
  if (query.isError) {
    if (query.error instanceof ApiRequestError && query.error.code === "not_found") {
      return <CaseNotFound caseId={caseId} />;
    }
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  }
  // A new case starts a fresh replay (clock, revealed sets, "surgery ends").
  return <ControlRoom key={query.data.case.id} detail={query.data} />;
}

function ControlRoom({ detail }: { detail: CaseDetail }) {
  const { t } = useTranslation();
  const lang = useLang();
  const pick = useBilingual();
  const title = pick(detail.case.title);

  const player = useRef<VideoPlayerHandle>(null);
  const getVideo = useCallback(() => player.current?.getVideo() ?? null, []);
  const seek = useCallback((seconds: number) => player.current?.seekTo(seconds), []);
  const clock = useVideoClock(getVideo);
  const duration = useMediaDuration(clock, detail.case.duration_s);

  const procedure = procedureOf(detail.timeline.steps[0]?.step_id ?? detail.moments.moments[0]?.step_id);
  const reference = useReference(procedure);
  const lookup = useMemo(() => buildReferenceLookup(reference.data), [reference.data]);

  const [chosenTrack, setChosenTrack] = useState<StepTrack | null>(null);
  const tracks = useMemo(() => availableTracks(detail.timeline.steps), [detail]);
  const track = selectTrack(detail.timeline.steps, detail.case.default_step_track, chosenTrack);
  const index = useMemo(() => buildReplayIndex(detail, track), [detail, track]);
  const state = useReplayState(clock, index);

  const revealedSteps = useMemo(() => index.steps.slice(0, state.steps), [index, state.steps]);
  const revealedMoments = useMemo(() => index.moments.slice(0, state.moments), [index, state.moments]);
  const revealedEvents = useMemo(() => index.events.slice(0, state.events), [index, state.events]);
  const revealedUtterances = useMemo(() => index.utterances.slice(0, state.utterances), [index, state.utterances]);
  const graph = useMemo(
    () => buildGraphElements(detail, reference.data, { steps: revealedSteps, moments: revealedMoments }, lang),
    [detail, reference.data, revealedSteps, revealedMoments, lang],
  );

  const surgery = useSurgeryEnds(detail.case.id, clock, detail.case.duration_s);

  return (
    <article className="flex min-w-0 flex-col gap-4">
      <Link
        to={`/cases/${encodeURIComponent(detail.case.id)}`}
        className="self-start text-sm text-primary underline-offset-4 hover:underline"
      >
        <span aria-hidden="true">← </span>
        {t("controlRoom.backToCase")}
      </Link>

      <header className="flex flex-col gap-1.5">
        <h1 className="m-0 text-2xl font-semibold tracking-tight">{t("controlRoom.title")}</h1>
        <p className="m-0 text-base font-medium">{title}</p>
        <p className="m-0 max-w-3xl text-sm text-muted-foreground">{t("controlRoom.intro")}</p>
        <TrustBadgeList labels={detail.trust_labels} />
      </header>

      {surgery.ended && <SurgeryEndedPanel event={surgery.ended} caseTitle={title} />}
      {surgery.failed && (
        <div role="alert" className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-card p-3 text-sm">
          <span>{t("ended.postError")}</span>
          <Button size="sm" variant="outline" onClick={surgery.retry}>
            {t("status.retry")}
          </Button>
        </div>
      )}

      <div className="grid min-w-0 grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(380px,500px)]">
        <section aria-label={t("controlRoom.video")} className="flex min-w-0 flex-col gap-3">
          <VideoPlayer
            ref={player}
            src={detail.media.video}
            poster={detail.media.poster}
            title={title}
            durationHint={detail.case.duration_s}
          />
          <StepBar
            index={index}
            state={state}
            duration={duration}
            lookup={lookup}
            tracks={tracks}
            onTrackChange={setChosenTrack}
            onSeek={seek}
            clock={clock}
          />
          <EventStrip events={revealedEvents} duration={duration} onSeek={seek} clock={clock} />
          <TranscriptTicker utterances={revealedUtterances} onSeek={seek} />
        </section>

        <div aria-label={t("controlRoom.graphColumn")} role="region" className="flex min-w-0 flex-col gap-4">
          <AlertsPanel moments={revealedMoments} lookup={lookup} onSeek={seek} />
          <GraphPanel elements={graph} onSeek={seek} />
        </div>
      </div>
    </article>
  );
}
