import {
  ExternalLink,
  Headphones,
  ListMusic,
  Volume2,
  VolumeX,
  SkipBack,
  SkipForward,
  Play,
  Pause,
  Repeat,
  Repeat1,
  X,
} from "lucide-react";
import { useCallback, useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { useCrateStore } from "../stores/crateStore";
import { useDigTrailStore } from "../stores/digTrailStore";
import { useLikesStore } from "../stores/likesStore";
import { usePlayerStore } from "../stores/playerStore";
import { useSettingsStore } from "../stores/settingsStore";
import { Artwork, DownloadButton, KeyPill } from "./ui";
import { fmtBpm, fmtClock } from "../lib/format";

export function PlayerDock() {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const {
    current,
    playing,
    currentTime,
    duration,
    muted,
    volume,
    repeat,
    attach,
    toggle,
    next,
    previous,
    nudge,
    setVolume,
    toggleMute,
    cycleRepeat,
    _onTimeUpdate,
    _onEnded,
    _onAudioError,
    playbackError,
    clearError,
  } = usePlayerStore();
  const crate = useCrateStore((s) => s.tracks);
  const toggleCrate = useCrateStore((s) => s.toggle);
  const heardIds = useLikesStore((s) => s.heardIds);
  const toggleHeard = useLikesStore((s) => s.toggleHeard);
  const pushSeed = useDigTrailStore((s) => s.push);
  const seekStepSec = useSettingsStore((s) => s.seekStepSec);
  const heard = current ? heardIds.has(current.id) : false;

  const seekRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;
    attach(el);
    const onTime = () => _onTimeUpdate(el.currentTime, el.duration || 0);
    const onPlay = () => usePlayerStore.setState({ playing: true });
    const onPause = () => usePlayerStore.setState({ playing: false });
    const onError = () => _onAudioError("Audio failed to load — preview expired or missing");
    el.addEventListener("timeupdate", onTime);
    el.addEventListener("durationchange", onTime);
    el.addEventListener("ended", _onEnded);
    el.addEventListener("play", onPlay);
    el.addEventListener("pause", onPause);
    el.addEventListener("error", onError);
    return () => {
      el.removeEventListener("timeupdate", onTime);
      el.removeEventListener("durationchange", onTime);
      el.removeEventListener("ended", _onEnded);
      el.removeEventListener("play", onPlay);
      el.removeEventListener("pause", onPause);
      el.removeEventListener("error", onError);
    };
  }, [attach, _onTimeUpdate, _onEnded, _onAudioError]);

  const onScrub = useCallback(
    (clientX: number) => {
      const bar = seekRef.current;
      if (!bar || !duration) return;
      const rect = bar.getBoundingClientRect();
      const ratio = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
      usePlayerStore.getState().seek(ratio * duration);
    },
    [duration],
  );

  const dragging = useRef(false);
  const pct = duration > 0 ? Math.min(100, (currentTime / duration) * 100) : 0;

  return (
    <footer
      className="fixed inset-x-0 bottom-0 z-40 hidden lg:block"
      style={{
        height: 84,
        background: "rgba(12, 12, 14, 0.86)",
        backdropFilter: "blur(26px) saturate(150%)",
        WebkitBackdropFilter: "blur(26px) saturate(150%)",
        borderTop: "1px solid rgba(255, 255, 255, 0.1)",
        boxShadow: "inset 0 1px 0 rgba(255, 255, 255, 0.07)",
      }}
      data-testid="player-dock"
    >
      <audio ref={audioRef} preload="metadata" />
      <div className="grid h-full grid-cols-[minmax(330px,430px)_minmax(0,1fr)_minmax(240px,300px)] items-center gap-4 px-5">
        {/* left — deck identity */}
        <div className="flex min-w-0 items-center gap-3">
          {current ? (
            <>
              <Artwork
                track={current}
                size={48}
                className="!rounded-[10px] ring-1 ring-white/12"
              />
              <div className="min-w-[120px] flex-1">
                <div className="flex items-center gap-2">
                  <span
                    className="rounded-pill border px-1.5 py-px font-mono text-[8px] uppercase tracking-[0.12em]"
                    style={
                      current.has_local_file
                        ? {
                            borderColor:
                              "color-mix(in srgb, var(--color-ok) 45%, transparent)",
                            color: "var(--color-ok)",
                          }
                        : {
                            borderColor: "rgba(255,255,255,0.16)",
                            color: "var(--color-ink-faint)",
                          }
                    }
                  >
                    {current.has_local_file ? "Local" : "Preview"}
                  </span>
                </div>
                <p className="mt-1 truncate text-[13px] font-medium leading-tight text-heading">
                  {current.title}
                </p>
                <p className="truncate text-[11px] leading-tight text-ink-dim">
                  {current.artist}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <button
                  type="button"
                  onClick={() => void toggleHeard(current.id, !heard)}
                  className={`flex h-9 w-9 items-center justify-center rounded-full transition-colors hover:bg-white/10 ${
                    heard ? "text-accent" : "text-ink-faint hover:text-heading"
                  }`}
                  aria-label={heard ? "Unmark heard" : "Mark heard"}
                  title={heard ? "Marked heard (click to unmark)" : "Mark heard"}
                  aria-pressed={heard}
                >
                  <Headphones size={15} />
                </button>
                <DownloadButton track={current} />
                {current.store_url ? (
                  <a
                    href={current.store_url}
                    target="_blank"
                    rel="noreferrer"
                    className="hidden h-9 items-center gap-1 rounded-full border border-line px-2 font-mono text-[9px] uppercase tracking-[0.14em] text-ink-dim transition-colors hover:border-line-strong hover:text-heading md:flex xl:px-2.5"
                    aria-label="Open on iTunes"
                    title="Open this track on iTunes"
                  >
                    <span className="hidden xl:inline">STORE</span>
                    <ExternalLink size={11} />
                  </a>
                ) : null}
                <Link
                  to={`/dig?mode=match&seed=${encodeURIComponent(current.id)}`}
                  onClick={() => pushSeed(current)}
                  className="hidden h-9 items-center gap-1 rounded-full border border-line px-2.5 font-mono text-[9px] uppercase tracking-[0.14em] text-ink-dim transition-colors hover:border-accent/60 hover:text-accent md:flex"
                  title="Dig tracks similar to this one"
                >
                  DIG &gt;
                </Link>
              </div>
            </>
          ) : (
            <div className="flex items-center gap-3">
              <span className="flex h-[48px] w-[48px] items-center justify-center rounded-[10px] border border-line bg-panel-2 text-ink-faint">
                <ListMusic size={16} />
              </span>
              <span className="text-[12px] text-ink-faint">
                No track loaded
                <span className="mt-0.5 block text-[11px] text-ink-dim">
                  Pick a row to load the deck
                </span>
              </span>
            </div>
          )}
        </div>

        {/* centre — transport above the scrubber */}
        <div className="flex min-w-0 flex-col items-center gap-1.5">
          {playbackError ? (
            <div
              role="alert"
              className="flex max-w-full items-center gap-2 rounded-pill border border-danger/40 bg-danger/10 px-2.5 py-0.5 font-mono text-[10px] text-danger"
            >
              <span className="truncate">{playbackError}</span>
              <button
                type="button"
                onClick={clearError}
                className="shrink-0 text-danger/80 hover:text-danger"
                aria-label="Dismiss audio error"
              >
                <X size={11} />
              </button>
            </div>
          ) : null}
          <div className="flex items-center gap-2.5">
            <button
              type="button"
              className="flex h-9 w-9 items-center justify-center rounded-full text-ink-dim transition-colors hover:bg-white/10 hover:text-heading disabled:opacity-30"
              onClick={previous}
              aria-label="Previous track"
              disabled={!current}
            >
              <SkipBack size={17} />
            </button>
            <button
              type="button"
              className="flex h-10 w-10 items-center justify-center rounded-full bg-white text-black transition-transform duration-150 hover:scale-[1.04] active:scale-95 disabled:opacity-40"
              onClick={toggle}
              disabled={!current}
              aria-label={playing ? "Pause" : "Play"}
            >
              {playing ? (
                <Pause size={16} fill="currentColor" />
              ) : (
                <Play size={16} fill="currentColor" className="ml-0.5" />
              )}
            </button>
            <button
              type="button"
              className="flex h-9 w-9 items-center justify-center rounded-full text-ink-dim transition-colors hover:bg-white/10 hover:text-heading disabled:opacity-30"
              onClick={next}
              aria-label="Next track"
              disabled={!current}
            >
              <SkipForward size={17} />
            </button>
            <button
              type="button"
              className="flex h-9 w-9 items-center justify-center rounded-full transition-colors hover:bg-white/10"
              onClick={cycleRepeat}
              aria-label={`Repeat mode: ${repeat}`}
            >
              {repeat === "one" ? (
                <Repeat1 size={15} className="text-accent" />
              ) : (
                <Repeat
                  size={15}
                  className={repeat === "off" ? "text-ink-faint" : "text-accent"}
                />
              )}
            </button>
          </div>
          <div className="flex w-full items-center gap-2.5">
            <span
              className="font-num w-9 shrink-0 text-right text-[10px] text-ink-dim"
              data-testid="clock"
            >
              {fmtClock(currentTime)}
            </span>
            <div
              ref={seekRef}
              role="slider"
              tabIndex={0}
              aria-label="Seek"
              aria-valuemin={0}
              aria-valuemax={Math.round(duration || 0)}
              aria-valuenow={Math.round(currentTime)}
              className="group relative h-5 min-w-0 flex-1 cursor-pointer"
              onPointerDown={(e) => {
                dragging.current = true;
                (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
                onScrub(e.clientX);
              }}
              onPointerMove={(e) => {
                if (dragging.current) onScrub(e.clientX);
              }}
              onPointerUp={() => {
                dragging.current = false;
              }}
              onKeyDown={(e) => {
                if (e.key === "ArrowRight") nudge(seekStepSec);
                if (e.key === "ArrowLeft") nudge(-seekStepSec);
              }}
            >
              <div className="pointer-events-none absolute inset-x-0 top-1/2 h-[2px] -translate-y-1/2 overflow-hidden bg-line">
                <div
                  className="h-full bg-accent"
                  style={{ width: `${pct}%` }}
                />
              </div>
              <span
                aria-hidden
                className="pointer-events-none absolute top-1/2 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100"
                style={{ left: `${pct}%`, background: "var(--color-accent)" }}
              />
            </div>
            <span className="font-num w-9 shrink-0 text-[10px] text-ink-faint">
              {fmtClock(duration || current?.duration_seconds)}
            </span>
          </div>
        </div>

        {/* right — harmony + level + crate */}
        <div className="flex min-w-0 items-center justify-end gap-3 border-l border-line pl-4">
          <div className="text-right">
            <p className="eyebrow !text-[8px]">Tempo</p>
            <p className="readout text-[15px] leading-none">
              {current ? fmtBpm(current.bpm) : "--"}
              <span className="ml-1 font-mono text-[8px] tracking-[0.1em] text-ink-faint">
                BPM
              </span>
            </p>
          </div>
          <div className="text-right">
            <p className="eyebrow !text-[8px]">Key</p>
            {current?.key ? (
              <KeyPill k={current.key} className="mt-0.5" />
            ) : (
              <span className="font-mono text-[11px] text-ink-faint">--</span>
            )}
          </div>
          <span className="h-8 w-px bg-line" aria-hidden />
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              className="btn btn-ghost !min-h-0 !border-0 !bg-transparent p-1.5 text-ink-dim hover:text-heading"
              onClick={toggleMute}
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
              className="hidden h-6 w-16 cursor-pointer accent-accent xl:block"
            />
          </div>
          <button
            type="button"
            className="btn !min-h-0 h-9 gap-1.5 px-2.5 text-[9px]"
            onClick={toggleCrate}
            aria-label={`Open Set Crate (${crate.length} ${crate.length === 1 ? "track" : "tracks"})`}
          >
            <ListMusic size={14} />
            Crate
            <span className="font-num text-[10px] text-accent" data-testid="crate-count">
              {crate.length}
            </span>
          </button>
        </div>
      </div>
    </footer>
  );
}
