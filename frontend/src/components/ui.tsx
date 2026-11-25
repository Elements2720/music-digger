import { Heart, ExternalLink, Pause, Play, Plus, Sparkles } from "lucide-react";
import { useState } from "react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useLikesStore } from "../stores/likesStore";
import { useCrateStore } from "../stores/crateStore";
import { usePlayerStore } from "../stores/playerStore";
import { useDigTrailStore } from "../stores/digTrailStore";
import { api } from "../api/client";
import type { TasteRankedMatch, Track } from "../types/apiTypes";
import { fmtBpm, hueOf, initials } from "../lib/format";
import { camelotColor } from "../lib/camelot";

// --------------------------------------------------------------- artwork

export function Artwork({
  track,
  size = 40,
  className = "",
  fluid = false,
}: {
  track: Pick<Track, "artwork_url" | "title" | "artist" | "id">;
  size?: number;
  className?: string;
  fluid?: boolean;
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
        style={fluid ? undefined : { width: size, height: size }}
      />
    );
  }
  return (
    <div
      aria-hidden
      className={`flex shrink-0 items-center justify-center rounded-[3px] font-mono text-[10px] text-ink ${className}`}
      style={{
        ...(fluid ? {} : { width: size, height: size }),
        background: `linear-gradient(135deg, hsl(${hue} 22% 18%), hsl(${(hue + 40) % 360} 28% 10%))`,
      }}
    >
      {initials(track)}
    </div>
  );
}

// ---------------------------------------------------------------- badges

export function KeyPill({
  k,
  className = "",
}: {
  k: string | null | undefined;
  className?: string;
}) {
  const tone = camelotColor(k);
  if (!k) {
    return <span className={`pill font-num text-ink-faint ${className}`}>—</span>;
  }
  if (!tone) return <span className={`pill pill-key font-num ${className}`}>{k}</span>;
  return (
    <span
      className={`pill font-num ${className}`}
      style={{ color: tone.color, borderColor: tone.border, background: tone.bg }}
      title={`Camelot ${tone.key}`}
    >
      {tone.key}
    </span>
  );
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

export function TasteBadgeCompact({ percent }: { percent: number }) {
  return (
    <span
      className="pill font-num"
      style={{
        borderColor: "color-mix(in srgb, var(--color-accent) 55%, transparent)",
        color: "var(--color-accent)",
      }}
    >
      {percent}%
    </span>
  );
}

export function LocalBadge({ has }: { has: boolean }) {
  if (!has) return null;
  return (
    <span
      className="pill font-num"
      style={{ color: "var(--color-ok)", borderColor: "var(--color-line)" }}
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
  const pushSeed = useDigTrailStore((s) => s.push);
  return (
    <Link
      to={`/dig?mode=match&seed=${encodeURIComponent(track.id)}`}
      onClick={() => pushSeed(track)}
      className="btn btn-ghost !min-h-0 gap-1 px-1.5 py-2 font-mono text-[9px] sm:px-2"
      aria-label={`Dig tracks similar to ${track.title}`}
      title="Dig similar tracks"
    >
      <Sparkles size={14} className="sm:hidden" />
      <span className="hidden sm:inline">DIG</span>
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
  note,
}: {
  track: Track;
  queue?: Track[];
  index?: number;
  trailing?: ReactNode;
  showMatch?: number | null;
  note?: ReactNode;
}) {
  const { heard, toggleHeard, addToCrate, inCrate, play } = useTrackActions();
  const current = usePlayerStore((s) => s.current);
  const isCurrent = current?.id === track.id;
  const isHeardNow = heard.has(track.id);
  const inCrateNow = inCrate.some((t) => t.id === track.id);

  return (
    <div
      className={`group flex flex-wrap items-center gap-2 border-b border-line px-2 py-2 transition-colors sm:gap-3 sm:px-3 ${
        isCurrent ? "bg-fill" : "hover:bg-fill"
      }`}
    >
      {index != null ? (
        <span className="font-num w-5 shrink-0 text-right text-[11px] text-ink-faint">
          {index + 1}
        </span>
      ) : null}
      <button
        type="button"
        onClick={() => play(track, queue)}
        className="btn btn-ghost !min-h-0 shrink-0 !border-0 !bg-transparent !p-0"
        aria-label={`Play ${track.title} by ${track.artist}`}
      >
        <Artwork
          track={track}
          size={40}
          className="!rounded-[3px] ring-1 ring-white/5 transition-transform duration-200 group-hover:scale-[1.03]"
        />
      </button>
      <button
        type="button"
        onClick={() => play(track, queue)}
        className="min-w-0 flex-1 overflow-hidden text-left"
      >
        <p
          className={`line-clamp-3 break-words text-[13px] leading-snug sm:line-clamp-2 sm:text-sm ${isCurrent ? "text-accent" : "text-heading"}`}
        >
          {track.title}
        </p>
        <p className="line-clamp-3 break-words text-xs leading-snug text-ink-dim sm:line-clamp-2">
          {track.artist}
        </p>
        {note ? (
          <p className="font-num mt-0.5 text-[10px] leading-tight text-ink-faint">{note}</p>
        ) : null}
        <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 font-num text-[10px] text-ink-faint md:hidden">
          <span>{fmtBpm(track.bpm)} BPM</span>
          {track.key ? (
            <KeyPill k={track.key} className="!px-1.5 !py-0 !text-[9px]" />
          ) : null}
          {track.has_local_file ? (
            <span style={{ color: "var(--color-ok)" }}>LOCAL</span>
          ) : null}
        </span>
      </button>
      <div className="hidden shrink-0 items-center gap-2 md:flex">
        {showMatch != null ? <TasteBadge percent={showMatch} /> : null}
        <BpmPill bpm={track.bpm} />
        <KeyPill k={track.key} />
      </div>
      <div className="track-actions flex shrink-0 basis-full items-center justify-end gap-0.5 sm:basis-auto sm:justify-start sm:gap-1">
        <button
          type="button"
          onClick={() => void toggleHeard(track)}
          className="btn btn-ghost !min-h-0 !border-0 !bg-transparent p-1.5 hover:!bg-fill"
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
          className="btn btn-ghost !min-h-0 gap-1 px-1.5 py-2 font-mono text-[9px] sm:px-2"
          aria-label={`Add ${track.title} to Set Crate`}
          title="Add to Set Crate"
        >
          <Plus size={14} className="sm:hidden" />
          <span className="hidden sm:inline">
            {inCrateNow ? "IN SET" : "+ SET"}
          </span>
        </button>
        <DigLink track={track} />
        <DownloadButton track={track} />
        <ItunesLink track={track} />
        {trailing ? <span className="flex items-center border-l border-line pl-1 sm:pl-1.5">{trailing}</span> : null}
      </div>
    </div>
  );
}

// --------------------------------------------------------- album shelves

export function AlbumCard({
  track,
  queue,
  eyebrow,
}: {
  track: Track;
  queue?: Track[];
  eyebrow?: string;
}) {
  const play = usePlayerStore((s) => s.play);
  const current = usePlayerStore((s) => s.current);
  const playing = usePlayerStore((s) => s.playing);
  const toggle = usePlayerStore((s) => s.toggle);
  const isCurrent = current?.id === track.id;
  return (
    <div className="card-lift w-[144px] shrink-0 sm:w-[164px]">
      <div className="relative aspect-square overflow-hidden rounded-[10px] border border-line bg-fill">
        <Artwork
          track={track}
          fluid
          className="!h-full !w-full !rounded-none"
        />
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/80 via-black/10 to-transparent" />
        <button
          type="button"
          onClick={() => (isCurrent ? toggle() : play(track, queue))}
          className="absolute bottom-2 right-2 flex h-10 w-10 items-center justify-center rounded-full bg-white text-black shadow-[0_10px_24px_-12px_rgba(0,0,0,0.9)] transition-transform duration-200 hover:scale-105 focus-visible:scale-105"
          aria-label={
            isCurrent && playing
              ? `Pause ${track.title}`
              : `Play ${track.title} by ${track.artist}`
          }
        >
          {isCurrent && playing ? (
            <Pause size={15} fill="currentColor" />
          ) : (
            <Play size={15} fill="currentColor" className="ml-0.5" />
          )}
        </button>
        {eyebrow ? (
          <span className="absolute left-2 top-2 rounded-pill border border-white/20 bg-black/60 px-2 py-0.5 font-mono text-[9px] uppercase tracking-[0.12em] text-ink-dim backdrop-blur-sm">
            {eyebrow}
          </span>
        ) : null}
      </div>
      <p className="mt-2 line-clamp-2 break-words text-[13px] leading-snug text-heading">
        {track.title}
      </p>
      <p className="line-clamp-1 break-words text-[11px] text-ink-dim">{track.artist}</p>
      <div className="mt-1 flex items-center gap-1.5">
        <span className="font-num text-[10px] text-ink-faint">
          {fmtBpm(track.bpm)} BPM
        </span>
        <KeyPill k={track.key} className="!px-1.5 !py-0 !text-[9px]" />
        {track.has_local_file ? (
          <span className="font-num text-[9px]" style={{ color: "var(--color-ok)" }}>
            LOCAL
          </span>
        ) : null}
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
