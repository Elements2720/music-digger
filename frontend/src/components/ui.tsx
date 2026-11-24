import { Heart, ExternalLink } from "lucide-react";
import { useState } from "react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useLikesStore } from "../stores/likesStore";
import { useCrateStore } from "../stores/crateStore";
import { usePlayerStore } from "../stores/playerStore";
import { api } from "../api/client";
import type { TasteRankedMatch, Track } from "../types/apiTypes";
import { fmtBpm, hueOf, initials } from "../lib/format";

// --------------------------------------------------------------- artwork

export function Artwork({
  track,
  size = 40,
  className = "",
}: {
  track: Pick<Track, "artwork_url" | "title" | "artist" | "id">;
  size?: number;
  className?: string;
}) {
  const hue = hueOf(track.artist + track.title);
  if (track.artwork_url) {
    return (
      <img
        src={track.artwork_url}
        alt=""
        width={size}
        height={size}
        loading="lazy"
        className={`shrink-0 rounded-[3px] object-cover ${className}`}
        style={{ width: size, height: size }}
      />
    );
  }
  return (
    <div
      aria-hidden
      className={`flex shrink-0 items-center justify-center rounded-[3px] font-mono text-[10px] text-ink ${className}`}
      style={{
        width: size,
        height: size,
        background: `linear-gradient(135deg, hsl(${hue} 22% 18%), hsl(${(hue + 40) % 360} 28% 10%))`,
      }}
    >
      {initials(track)}
    </div>
  );
}

// ---------------------------------------------------------------- badges

export function KeyPill({ k }: { k: string | null | undefined }) {
  if (!k) return <span className="pill font-num text-ink-faint">—</span>;
  return <span className="pill pill-key font-num">{k}</span>;
}

export function BpmPill({ bpm }: { bpm: number | null | undefined }) {
  return <span className="pill font-num">{bpm == null ? "—" : fmtBpm(bpm)} BPM</span>;
}

export function TasteBadge({ percent }: { percent: number }) {
  return (
    <span
      className="pill font-num"
      style={{
        borderColor: "color-mix(in srgb, var(--color-accent) 55%, transparent)",
        color: "var(--color-accent)",
      }}
    >
      {percent}% MATCH
    </span>
  );
}

export function LocalBadge({ has }: { has: boolean }) {
  if (!has) return null;
  return (
    <span
      className="pill font-num"
      style={{ color: "var(--color-accent)", borderColor: "var(--color-line)" }}
    >
      LOCAL
    </span>
  );
}

export function SourcePill({ source }: { source: string | null | undefined }) {
  if (!source) return null;
  return <span className="pill font-num uppercase text-ink-dim">{source}</span>;
}

// ------------------------------------------------------- download action

export function DownloadButton({ track }: { track: Track }) {
  const [state, setState] = useState<"idle" | "busy" | "done" | "error">(
    track.has_local_file ? "done" : "idle",
  );
  const [message, setMessage] = useState<string | null>(null);

  if (state === "done") return <LocalBadge has />;

  const download = async () => {
    setState("busy");
    setMessage(null);
    try {
      await api.downloadTrack(track.id);
      setState("done");
    } catch (err) {
      setState("error");
      setMessage(err instanceof Error ? err.message : "Download failed");
    }
  };

  return (
    <span className="flex items-center gap-1">
      <button
        type="button"
        onClick={() => void download()}
        disabled={state === "busy"}
        className="btn btn-ghost !min-h-0 px-2 py-2 font-mono text-[10px]"
        aria-label={`Download ${track.title}`}
        title={message ?? "Download full track from source"}
      >
        {state === "busy" ? "…" : state === "error" ? "RETRY" : "↓ DL"}
      </button>
    </span>
  );
}

function ItunesLink({ track }: { track: Track }) {
  const url = track.store_url ?? track.preview_url;
  if (!url) return null;
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      className="btn btn-ghost !min-h-0 p-2 font-mono text-[10px] text-ink-faint hover:text-heading"
      aria-label={`Open ${track.title} on iTunes`}
      title="Open on iTunes"
    >
      <ExternalLink size={14} />
      <span className="hidden lg:inline">iTUNES</span>
    </a>
  );
}

function DigLink({ track }: { track: Track }) {
  return (
    <Link
      to={`/dig?mode=match&seed=${encodeURIComponent(track.id)}`}
      className="btn btn-ghost !min-h-0 px-2 py-2 font-mono text-[10px]"
      aria-label={`Dig tracks similar to ${track.title}`}
      title="Dig similar tracks"
    >
      DIG
    </Link>
  );
}

// ------------------------------------------------------------- feedback

export function Loading({ label = "LOADING…" }: { label?: string }) {
  return (
    <div className="panel flex items-center justify-center p-10">
      <span className="eyebrow animate-pulse">{label}</span>
    </div>
  );
}

export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string;
  hint?: string;
  action?: ReactNode;
}) {
  return (
    <div className="panel flex flex-col items-center gap-3 p-10 text-center">
      <p className="font-mono text-xs uppercase tracking-[0.14em] text-ink-dim">
        {title}
      </p>
      {hint ? <p className="max-w-sm text-xs text-ink-faint">{hint}</p> : null}
      {action}
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="panel p-6">
      <p className="font-mono text-xs uppercase tracking-[0.1em] text-danger">
        ERROR
      </p>
      <p className="mt-2 text-sm text-ink-dim">{message}</p>
    </div>
  );
}

export function PanelHead({
  title,
  right,
}: {
  title: string;
  right?: ReactNode;
}) {
  return (
    <div className="panel-head">
      <span className="eyebrow">{title}</span>
      {right}
    </div>
  );
}

// ------------------------------------------------------------ track rows

function useTrackActions() {
  const heard = useLikesStore((s) => s.heardIds);
  const toggleHeardLocal = useLikesStore((s) => s.toggleHeard);
  const addToCrate = useCrateStore((s) => s.add);
  const inCrate = useCrateStore((s) => s.tracks);
  const play = usePlayerStore((s) => s.play);

  const toggleHeard = async (track: Track) => {
    const next = !heard.has(track.id);
    toggleHeardLocal(track.id, next);
    try {
      await api.setHeard(track.id, next);
    } catch {
      toggleHeardLocal(track.id, !next);
    }
  };

  return { heard, toggleHeard, addToCrate, inCrate, play };
}

export function TrackRow({
  track,
  queue,
  index,
  trailing,
  showMatch,
}: {
  track: Track;
  queue?: Track[];
  index?: number;
  trailing?: ReactNode;
  showMatch?: number | null;
}) {
  const { heard, toggleHeard, addToCrate, inCrate, play } = useTrackActions();
  const current = usePlayerStore((s) => s.current);
  const isCurrent = current?.id === track.id;
  const isHeardNow = heard.has(track.id);
  const inCrateNow = inCrate.some((t) => t.id === track.id);

  return (
    <div
      className={`flex items-center gap-3 border-b border-line px-3 py-2 transition-colors ${
        isCurrent ? "bg-panel-2" : "hover:bg-panel-2/60"
      }`}
    >
      {index != null ? (
        <span className="font-num w-6 text-right text-[11px] text-ink-faint">
          {index + 1}
        </span>
      ) : null}
      <button
        type="button"
        onClick={() => play(track, queue)}
        className="btn btn-ghost !min-h-0 shrink-0 !p-0"
        aria-label={`Play ${track.title} by ${track.artist}`}
      >
        <Artwork track={track} size={40} />
      </button>
      <button
        type="button"
        onClick={() => play(track, queue)}
        className="min-w-0 flex-1 text-left"
      >
        <p
          className={`truncate text-sm ${isCurrent ? "text-accent" : "text-heading"}`}
        >
          {track.title}
        </p>
        <p className="truncate text-xs text-ink-dim">{track.artist}</p>
      </button>
      <div className="hidden items-center gap-2 md:flex">
        {showMatch != null ? <TasteBadge percent={showMatch} /> : null}
        <BpmPill bpm={track.bpm} />
        <KeyPill k={track.key} />
      </div>
      <div className="flex shrink-0 items-center gap-1">
        <button
          type="button"
          onClick={() => void toggleHeard(track)}
          className="btn btn-ghost !min-h-0 p-2"
          aria-label={isHeardNow ? `Unlike ${track.title}` : `Like ${track.title}`}
          aria-pressed={isHeardNow}
        >
          <Heart
            size={16}
            className={isHeardNow ? "heart-on" : "text-ink-faint"}
            fill={isHeardNow ? "currentColor" : "none"}
          />
        </button>
        <button
          type="button"
          onClick={() => addToCrate(track)}
          disabled={inCrateNow}
          className="btn btn-ghost !min-h-0 px-2 py-2 font-mono text-[10px]"
          aria-label={`Add ${track.title} to Set Crate`}
        >
          {inCrateNow ? "IN CRATE" : "+ SET"}
        </button>
        <DigLink track={track} />
        <DownloadButton track={track} />
        <ItunesLink track={track} />
        {trailing}
      </div>
    </div>
  );
}

export function TasteRow({
  match,
  index,
}: {
  match: TasteRankedMatch;
  index: number;
}) {
  return (
    <TrackRow track={match} index={index} showMatch={Math.round(match.taste_percent)} />
  );
}
