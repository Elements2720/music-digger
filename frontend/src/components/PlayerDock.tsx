import { ListMusic, Volume2, VolumeX, SkipBack, SkipForward, Play, Pause, Repeat, Repeat1 } from "lucide-react";
import { useCallback, useEffect, useRef } from "react";
import { useCrateStore } from "../stores/crateStore";
import { usePlayerStore } from "../stores/playerStore";
import { DownloadButton } from "./ui";
import { fmtClock } from "../lib/format";

export function PlayerDock() {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const {
    current,
    playing,
    currentTime,
    duration,
    muted,
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
  } = usePlayerStore();
  const crate = useCrateStore((s) => s.tracks);
  const toggleCrate = useCrateStore((s) => s.toggle);

  const seekRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;
    attach(el);
    const onTime = () => _onTimeUpdate(el.currentTime, el.duration || 0);
    el.addEventListener("timeupdate", onTime);
    el.addEventListener("durationchange", onTime);
    el.addEventListener("ended", _onEnded);
    return () => {
      el.removeEventListener("timeupdate", onTime);
      el.removeEventListener("durationchange", onTime);
      el.removeEventListener("ended", _onEnded);
    };
  }, [attach, _onTimeUpdate, _onEnded]);

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

  return (
    <footer
      className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-panel"
      style={{ height: 72 }}
      data-testid="player-dock"
    >
      <audio ref={audioRef} preload="metadata" />
      <div className="flex h-full items-center gap-3 px-3 sm:px-4">
        {/* transport */}
        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            className="btn btn-ghost !min-h-0 p-2"
            onClick={previous}
            aria-label="Previous track"
          >
            <SkipBack size={18} />
          </button>
          <button
            type="button"
            className="btn btn-primary !min-h-0 p-2.5"
            onClick={toggle}
            disabled={!current}
            aria-label={playing ? "Pause" : "Play"}
          >
            {playing ? <Pause size={18} /> : <Play size={18} />}
          </button>
          <button
            type="button"
            className="btn btn-ghost !min-h-0 p-2"
            onClick={next}
            aria-label="Next track"
          >
            <SkipForward size={18} />
          </button>
        </div>

        {/* mini artwork + title */}
        <div className="hidden min-w-0 items-center gap-3 sm:flex sm:w-56">
          {current ? (
            <>
              <p className="min-w-0 flex-1">
                <span className="block truncate text-sm text-heading">
                  {current.title}
                </span>
                <span className="block truncate text-xs text-ink-dim">
                  {current.artist}
                </span>
              </p>
              <DownloadButton track={current} />
            </>
          ) : (
            <span className="eyebrow">NO TRACK LOADED</span>
          )}
        </div>

        {/* seek bar */}
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <span className="font-num hidden text-[11px] text-ink-dim sm:block" data-testid="clock">
            {fmtClock(currentTime)} / {fmtClock(duration || current?.duration_seconds)}
          </span>
          <div
            ref={seekRef}
            role="slider"
            tabIndex={0}
            aria-label="Seek"
            aria-valuemin={0}
            aria-valuemax={Math.round(duration || 0)}
            aria-valuenow={Math.round(currentTime)}
            className="group relative h-6 min-w-0 flex-1 cursor-pointer"
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
              if (e.key === "ArrowRight") nudge(5);
              if (e.key === "ArrowLeft") nudge(-5);
            }}
          >
            <div className="pointer-events-none absolute inset-x-0 top-1/2 h-[2px] -translate-y-1/2 bg-fill">
              <div
                className="h-full bg-accent"
                style={{
                  width: duration ? `${(currentTime / duration) * 100}%` : "0%",
                }}
              />
            </div>
          </div>
        </div>

        {/* right controls */}
        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            className="btn btn-ghost !min-h-0 p-2"
            onClick={cycleRepeat}
            aria-label={`Repeat mode: ${repeat}`}
          >
            {repeat === "one" ? <Repeat1 size={16} /> : <Repeat size={16} className={repeat === "off" ? "text-ink-faint" : "text-accent"} />}
          </button>
          <button
            type="button"
            className="btn btn-ghost !min-h-0 p-2"
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
            value={muted ? 0 : usePlayerStore.getState().volume}
            onChange={(e) => setVolume(Number(e.target.value))}
            aria-label="Volume"
            className="hidden h-1 w-20 accent-accent md:block"
          />
          <button
            type="button"
            className="btn btn-ghost !min-h-0 relative p-2"
            onClick={toggleCrate}
            aria-label={`Open Set Crate (${crate.length} tracks)`}
          >
            <ListMusic size={18} />
            {crate.length > 0 ? (
              <span
                className="font-num absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-accent px-1 text-[9px] text-canvas"
                data-testid="crate-count"
              >
                {crate.length}
              </span>
            ) : null}
          </button>
        </div>
      </div>
    </footer>
  );
}
