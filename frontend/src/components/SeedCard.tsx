import { Pause, Play, Plus, Sparkles } from "lucide-react";
import { useCrateStore } from "../stores/crateStore";
import { usePlayerStore } from "../stores/playerStore";
import type { Track } from "../types/apiTypes";
import { fmtBpm } from "../lib/format";
import { Artwork, DownloadButton, KeyPill, LocalBadge } from "./ui";

/** The selected seed, with its own transport so the DJ can A/B a match. */
export function SeedCard({ track, onVibe }: { track: Track; onVibe: () => void }) {
  const current = usePlayerStore((s) => s.current);
  const playing = usePlayerStore((s) => s.playing);
  const toggle = usePlayerStore((s) => s.toggle);
  const play = usePlayerStore((s) => s.play);
  const add = useCrateStore((s) => s.add);
  const inCrate = useCrateStore((s) => s.tracks.some((t) => t.id === track.id));

  const isThis = current?.id === track.id;
  const canPlay = Boolean(track.local_path || track.preview_url);

  return (
    <div
      className="panel relative overflow-hidden p-4 sm:p-5"
      style={{ borderLeft: "2px solid var(--color-accent)" }}
    >
      <span
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-px"
        style={{
          background:
            "linear-gradient(90deg, color-mix(in srgb, var(--color-accent) 55%, transparent), transparent 60%)",
        }}
      />
      <div className="relative flex items-start gap-4">
        <Artwork
          track={track}
          size={104}
          className="!h-24 !w-24 !rounded-[3px] ring-1 ring-white/10 sm:!h-[112px] sm:!w-[112px]"
        />
        <div className="min-w-0 flex-1">
          <p className="eyebrow">Selected seed track</p>
          <h2 className="mt-1 line-clamp-2 break-words text-[17px] leading-tight text-heading sm:text-xl">
            {track.title}
          </h2>
          <p className="truncate text-sm text-ink-dim">{track.artist}</p>

          <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
            <span className="pill font-num">{fmtBpm(track.bpm)} BPM</span>
            <KeyPill k={track.key} />
            <LocalBadge has={track.has_local_file} />
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => (isThis ? toggle() : play(track))}
              disabled={!canPlay}
              className="flex h-11 w-11 items-center justify-center rounded-[3px] transition-colors duration-150 hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
              style={{
                background: "var(--color-accent)",
                color: "var(--color-accent-ink)",
              }}
              aria-label={
                isThis && playing ? `Pause ${track.title}` : `Play ${track.title}`
              }
              title={canPlay ? undefined : "No local file or preview to play"}
            >
              {isThis && playing ? (
                <Pause size={17} fill="currentColor" />
              ) : (
                <Play size={17} fill="currentColor" className="ml-0.5" />
              )}
            </button>
            <button
              type="button"
              onClick={() => add(track)}
              disabled={inCrate}
              className="btn btn-ghost !min-h-0 px-2.5 py-2 font-mono text-[10px]"
              aria-label={`Add ${track.title} to Set Crate`}
            >
              <Plus size={13} />
              {inCrate ? "IN SET" : "SET"}
            </button>
            <DownloadButton track={track} />
            <button
              type="button"
              onClick={onVibe}
              className="btn btn-ghost !min-h-0 px-2.5 py-2 font-mono text-[10px]"
              aria-label="Open the catalog filtered by this seed's key"
            >
              <Sparkles size={13} />
              VIBE
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
