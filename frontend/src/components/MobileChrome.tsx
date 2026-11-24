import { Activity, ListMusic, Pause, Play, Settings2 } from "lucide-react";
import { NavLink } from "react-router-dom";
import { useCrateStore } from "../stores/crateStore";
import { usePlayerStore } from "../stores/playerStore";
import { Artwork } from "./ui";
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
            aria-label={`Open Set Crate (${crateCount} tracks)`}
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
                onClick={toggle}
                className="min-w-0 flex-1 text-left"
                aria-label={
                  playing ? `Pause ${current.title}` : `Play ${current.title}`
                }
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
                aria-label={playing ? "Pause" : "Play"}
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
    </div>
  );
}
