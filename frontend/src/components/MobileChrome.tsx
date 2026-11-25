import { Activity, ListMusic, Pause, Play, Settings2 } from "lucide-react";
import { NavLink } from "react-router-dom";
import { useCrateStore } from "../stores/crateStore";
import { usePlayerStore } from "../stores/playerStore";
import { useLikesStore } from "../stores/likesStore";
import { fmtBpm, fmtClock } from "../lib/format";
import { Artwork, DownloadButton, KeyPill } from "./ui";
import { Link } from "react-router-dom";
import { Heart, Volume2, VolumeX, Repeat, Repeat1, SkipBack, SkipForward, ChevronDown } from "lucide-react";
import { useState } from "react";
import { NAV_ITEMS } from "./Shell";

const SHORT_LABEL: Record<string, string> = {
  "/": "DASH",
  "/dig": "DIG",
  "/builder": "SET",
  "/mix": "MIX",
  "/library": "LIB",
  "/pipeline": "PIPE",
};

/** Settings lives in the header gear only — the bottom bar stays at six tabs. */
const BOTTOM_NAV = NAV_ITEMS.filter((item) => item.to !== "/settings");

/** Sticky mobile header, floating liquid-glass mini-player and bottom nav capsule. */
export function MobileChrome() {
  const current = usePlayerStore((s) => s.current);
  const playing = usePlayerStore((s) => s.playing);
  const toggle = usePlayerStore((s) => s.toggle);
  const progress = usePlayerStore((s) => s.currentTime);
  const duration = usePlayerStore((s) => s.duration);
  const crateCount = useCrateStore((s) => s.tracks.length);
  const toggleCrate = useCrateStore((s) => s.toggle);
  const [deckOpen, setDeckOpen] = useState(false);

  const pct = duration > 0 ? Math.min(100, (progress / duration) * 100) : 0;

  return (
    <div className="lg:hidden">
      <header
        className="fixed inset-x-0 top-0 z-30 flex h-14 items-center justify-between gap-3 border-b border-white/10 px-4"
        style={{
          background: "rgba(0, 0, 0, 0.72)",
          backdropFilter: "blur(24px) saturate(150%)",
          WebkitBackdropFilter: "blur(24px) saturate(150%)",
          boxShadow: "inset 0 1px 0 rgba(255,255,255,0.06)",
        }}
      >
        <div className="flex min-w-0 items-center gap-2.5">
          <span
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px]"
            style={{
              background: "var(--color-accent)",
              color: "var(--color-accent-ink)",
              boxShadow: "0 8px 20px -12px var(--color-accent)",
            }}
          >
            <Activity size={15} strokeWidth={2.4} />
          </span>
          <span className="min-w-0">
            <span className="block truncate font-mono text-[11px] font-semibold tracking-[0.22em] text-heading">
              DIGDEEPER
            </span>
            <span className="block truncate text-[10px] leading-tight text-ink-faint">
              Dig without leaving the room
            </span>
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={toggleCrate}
            className="relative flex h-11 w-11 items-center justify-center rounded-pill border border-white/12 bg-white/[0.04] text-ink-dim transition-colors active:bg-white/10"
            aria-label={`Open Set Crate (${crateCount} ${crateCount === 1 ? "track" : "tracks"})`}
          >
            <ListMusic size={16} />
            {crateCount > 0 ? (
              <span
                className="font-num absolute -right-0.5 -top-0.5 flex h-5 min-w-5 items-center justify-center rounded-pill px-1 text-[10px] font-semibold text-accent-ink"
                style={{ background: "var(--color-accent)" }}
              >
                {crateCount}
              </span>
            ) : null}
          </button>
          <NavLink
            to="/settings"
            className={({ isActive }) =>
              `flex h-11 w-11 items-center justify-center rounded-pill border transition-colors ${
                isActive
                  ? "border-accent/70 bg-accent/15 text-heading"
                  : "border-white/12 bg-white/[0.04] text-ink-dim active:bg-white/10"
              }`
            }
            aria-label="Settings"
            title="Settings"
          >
            <Settings2 size={17} />
          </NavLink>
        </div>
      </header>

      <div
        className="fixed inset-x-0 bottom-0 z-30 px-3"
        style={{ paddingBottom: "max(10px, env(safe-area-inset-bottom))" }}
      >
        {current ? (
          <div
            className="relative mb-2 overflow-hidden rounded-card border border-white/12 shadow-[0_24px_60px_-32px_rgba(0,0,0,1)]"
            style={{
              background: "rgba(22, 22, 26, 0.78)",
              backdropFilter: "blur(24px) saturate(160%)",
              WebkitBackdropFilter: "blur(24px) saturate(160%)",
              boxShadow:
                "inset 0 1px 0 rgba(255,255,255,0.1), 0 24px 60px -32px rgba(0,0,0,1)",
            }}
          >
            <span
              aria-hidden
              className="absolute inset-x-0 top-0 h-[2px]"
              style={{
                background: `linear-gradient(90deg, var(--color-accent) ${pct}%, rgba(255,255,255,0.12) ${pct}%)`,
              }}
            />
            <div className="flex items-center gap-2.5 py-2 pl-2 pr-2">
              <Artwork
                track={current}
                size={40}
                className="!rounded-[8px] ring-1 ring-white/10"
              />
              <button
                type="button"
                onClick={() => setDeckOpen(true)}
                className="min-w-0 flex-1 text-left"
                aria-label={`Expand deck — now playing ${current.title} by ${current.artist}`}
                aria-expanded={deckOpen}
                aria-controls="mobile-deck-sheet"
              >
                <p className="truncate text-[13px] leading-tight text-heading">
                  {current.title}
                </p>
                <p className="truncate text-[11px] leading-tight text-ink-faint">
                  {current.artist}
                </p>
              </button>
              <button
                type="button"
                onClick={toggle}
                className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-white text-black transition-transform active:scale-95 disabled:opacity-40"
                aria-label={playing ? `Pause ${current.title}` : `Play ${current.title}`}
              >
                {playing ? (
                  <Pause size={16} fill="currentColor" />
                ) : (
                  <Play size={16} fill="currentColor" className="ml-0.5" />
                )}
              </button>
            </div>
          </div>
        ) : null}

        <nav
          aria-label="Primary"
          className="flex items-stretch gap-0.5 rounded-pill border border-white/12 p-1"
          style={{
            background: "rgba(22, 22, 26, 0.78)",
            backdropFilter: "blur(24px) saturate(160%)",
            WebkitBackdropFilter: "blur(24px) saturate(160%)",
            boxShadow: "inset 0 1px 0 rgba(255,255,255,0.1)",
          }}
        >
          {BOTTOM_NAV.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                role="tab"
                data-tab-label={item.label}
                className={({ isActive }) =>
                  `relative flex min-h-11 min-w-0 flex-1 flex-col items-center justify-center gap-1 rounded-pill py-1.5 text-[9px] uppercase tracking-[0.1em] transition-colors ${
                    isActive ? "text-accent" : "text-ink-faint"
                  }`
                }
                aria-label={item.label}
              >
                {({ isActive }) => (
                  <>
                    <Icon size={17} strokeWidth={isActive ? 2.4 : 1.9} />
                    <span className="max-w-full truncate font-mono">
                      {SHORT_LABEL[item.to] ?? item.label}
                    </span>
                  </>
                )}
              </NavLink>
            );
          })}
        </nav>
      </div>

      {current ? (
        <MobileDeckSheet open={deckOpen} onClose={() => setDeckOpen(false)} />
      ) : null}
    </div>
  );
}

/** Full-screen expanded deck for touch screens — every dock control, reachable. */
function MobileDeckSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const current = usePlayerStore((s) => s.current);
  const playing = usePlayerStore((s) => s.playing);
  const toggle = usePlayerStore((s) => s.toggle);
  const next = usePlayerStore((s) => s.next);
  const previous = usePlayerStore((s) => s.previous);
  const currentTime = usePlayerStore((s) => s.currentTime);
  const duration = usePlayerStore((s) => s.duration);
  const muted = usePlayerStore((s) => s.muted);
  const volume = usePlayerStore((s) => s.volume);
  const setVolume = usePlayerStore((s) => s.setVolume);
  const toggleMute = usePlayerStore((s) => s.toggleMute);
  const cycleRepeat = usePlayerStore((s) => s.cycleRepeat);
  const repeat = usePlayerStore((s) => s.repeat);
  const heardIds = useLikesStore((s) => s.heardIds);
  const toggleHeard = useLikesStore((s) => s.toggleHeard);
  const [scrubRatio, setScrubRatio] = useState<number | null>(null);

  if (!open || !current) return null;

  const heard = heardIds.has(current.id);

  const scrub = (ratio: number) => {
    setScrubRatio(ratio);
    usePlayerStore.getState().seek(ratio * duration);
  };

  return (
    <div
      id="mobile-deck-sheet"
      role="dialog"
      aria-modal="true"
      aria-label={`Now playing — ${current.title}`}
      className="fixed inset-0 z-[70] flex flex-col lg:hidden"
      style={{ background: "rgba(0,0,0,0.92)", backdropFilter: "blur(28px)" }}
      onKeyDown={(e) => {
        if (e.key === "Escape") onClose();
      }}
      tabIndex={-1}
    >
      <div className="flex items-center justify-between px-4 pt-4">
        <button
          type="button"
          onClick={onClose}
          className="flex h-11 w-11 items-center justify-center rounded-pill border border-white/12 text-ink-dim active:bg-white/10"
          aria-label="Close deck"
        >
          <ChevronDown size={20} />
        </button>
        <p className="eyebrow !text-[9px]">NOW PLAYING</p>
        <span className="w-11" aria-hidden />
      </div>

      <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6">
        <Artwork
          track={current}
          size={192}
          className="!rounded-[20px] ring-1 ring-white/12"
        />
        <div className="min-w-0 text-center">
          <h2 className="truncate text-lg font-semibold text-heading">{current.title}</h2>
          <p className="truncate text-sm text-ink-dim">{current.artist}</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="readout text-[15px]">{current.bpm != null ? fmtBpm(current.bpm) : "--"}</span>
          <span className="eyebrow !text-[8px]">BPM</span>
          {current.key ? <KeyPill k={current.key} /> : null}
        </div>
      </div>

      <div className="flex flex-col gap-3 px-6 pb-[max(18px,env(safe-area-inset-bottom))]">
        <div className="flex items-center gap-2.5">
          <span className="font-num w-9 shrink-0 text-right text-[10px] text-ink-dim">
            {fmtClock(currentTime)}
          </span>
          <input
            type="range"
            min={0}
            max={1000}
            value={Math.round((scrubRatio ?? (duration > 0 ? currentTime / duration : 0)) * 1000)}
            onChange={(e) => scrub(Number(e.target.value) / 1000)}
            aria-label="Seek"
            aria-valuemin={0}
            aria-valuemax={Math.round(duration || 0)}
            aria-valuenow={Math.round(currentTime)}
            className="h-11 min-w-0 flex-1 accent-accent"
          />
          <span className="font-num w-9 shrink-0 text-[10px] text-ink-faint">
            {fmtClock(duration || current.duration_seconds)}
          </span>
        </div>

        <div className="flex items-center justify-center gap-5">
          <button
            type="button"
            onClick={previous}
            className="flex h-12 w-12 items-center justify-center rounded-full text-ink-dim active:bg-white/10"
            aria-label="Previous track"
          >
            <SkipBack size={20} />
          </button>
          <button
            type="button"
            onClick={toggle}
            className="flex h-16 w-16 items-center justify-center rounded-full bg-white text-black active:scale-95"
            aria-label={playing ? `Pause ${current.title}` : `Play ${current.title}`}
          >
            {playing ? (
              <Pause size={24} fill="currentColor" />
            ) : (
              <Play size={24} fill="currentColor" className="ml-1" />
            )}
          </button>
          <button
            type="button"
            onClick={next}
            className="flex h-12 w-12 items-center justify-center rounded-full text-ink-dim active:bg-white/10"
            aria-label="Next track"
          >
            <SkipForward size={20} />
          </button>
          <button
            type="button"
            onClick={cycleRepeat}
            className="flex h-12 w-12 items-center justify-center rounded-full active:bg-white/10"
            aria-label={`Repeat mode: ${repeat}`}
          >
            {repeat === "one" ? (
              <Repeat1 size={18} className="text-accent" />
            ) : (
              <Repeat size={18} className={repeat === "off" ? "text-ink-faint" : "text-accent"} />
            )}
          </button>
        </div>

        <div className="flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={toggleMute}
            className="flex h-11 w-11 items-center justify-center rounded-pill border border-white/12 text-ink-dim active:bg-white/10"
            aria-label={muted ? "Unmute" : "Mute"}
          >
            {muted ? <VolumeX size={16} /> : <Volume2 size={16} />}
          </button>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={muted ? 0 : volume}
            onChange={(e) => setVolume(Number(e.target.value))}
            aria-label="Volume"
            className="h-11 min-w-0 flex-1 accent-accent"
          />
          <button
            type="button"
            onClick={() => toggleHeard(current.id, !heard)}
            className={`flex h-11 w-11 items-center justify-center rounded-pill border border-white/12 active:bg-white/10 ${heard ? "text-accent" : "text-ink-faint"}`}
            aria-label={heard ? `Unmark ${current.title} heard` : `Mark ${current.title} heard`}
            aria-pressed={heard}
          >
            <Heart size={16} fill={heard ? "currentColor" : "none"} />
          </button>
          <DownloadButton track={current} />
        </div>

        <div className="flex items-center gap-2">
          {current.store_url ? (
            <a
              href={current.store_url}
              target="_blank"
              rel="noreferrer"
              className="btn !min-h-11 flex-1 gap-1.5 text-[10px]"
            >
              STORE <span aria-hidden>↗</span>
            </a>
          ) : null}
          <Link
            to={`/dig?mode=match&seed=${encodeURIComponent(current.id)}`}
            onClick={onClose}
            className="btn btn-primary !min-h-11 flex-1 gap-1.5 text-[10px]"
          >
            DIG &gt;
          </Link>
        </div>
      </div>
    </div>
  );
}
