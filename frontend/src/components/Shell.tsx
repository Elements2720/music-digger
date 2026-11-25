import {
  Activity,
  AudioWaveform,
  ChevronRight,
  Disc3,
  Gauge,
  Library,
  ListMusic,
  ListOrdered,
  PanelLeftClose,
  PanelLeftOpen,
  SlidersHorizontal,
  Workflow,
} from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { create } from "zustand";
import { api } from "../api/client";
import { useCrateStore } from "../stores/crateStore";

export const NAV_ITEMS = [
  { to: "/", label: "Dashboard", icon: Gauge },
  { to: "/dig", label: "Dig", icon: Disc3 },
  { to: "/builder", label: "Set Builder", icon: ListOrdered },
  { to: "/mix", label: "Mix Analyzer", icon: AudioWaveform },
  { to: "/library", label: "Library", icon: Library },
  { to: "/pipeline", label: "Pipeline", icon: Workflow },
  { to: "/settings", label: "Settings", icon: SlidersHorizontal },
] as const;

// ------------------------------------------------------------ shell state

interface ShellState {
  collapsed: boolean;
  setCollapsed: (next: boolean) => void;
}

export const useShellStore = create<ShellState>()((set) => ({
  collapsed:
    typeof window === "undefined"
      ? false
      : window.localStorage.getItem("shell-collapsed") === "1",
  setCollapsed: (next) => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem("shell-collapsed", next ? "1" : "0");
    }
    set({ collapsed: next });
  },
}));

// ------------------------------------------------------------ api status

export function ApiStatus({ compact = false }: { compact?: boolean }) {
  const [online, setOnline] = useState<boolean | null>(null);
  useEffect(() => {
    let alive = true;
    const check = () =>
      api
        .health()
        .then(() => alive && setOnline(true))
        .catch(() => alive && setOnline(false));
    void check();
    const timer = window.setInterval(check, 30000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, []);

  const tone =
    online === true
      ? "var(--color-ok)"
      : online === false
        ? "var(--color-danger)"
        : "var(--color-ink-faint)";

  if (compact) {
    return (
      <span
        className="inline-flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.12em] text-ink-faint"
        title={online === false ? "Backend unreachable" : "Local backend"}
      >
        <span
          aria-hidden
          className="h-1.5 w-1.5"
          style={{ background: tone }}
        />
        {online === false ? "OFFLINE" : "API"}
      </span>
    );
  }

  return (
    <div
      className="flex min-w-0 items-center gap-2 border border-line bg-panel-2 px-2.5 py-2.5"
      title={online === false ? "Backend unreachable" : "Local backend · checked every 30s"}
    >
      <span
        aria-hidden
        className="h-1.5 w-1.5 shrink-0"
        style={{ background: tone, boxShadow: `0 0 6px ${tone}` }}
      />
      <span className="truncate font-mono text-[9px] uppercase tracking-[0.1em] text-ink-dim">
        {online === false ? "API OFFLINE" : "API ONLINE"}
      </span>
    </div>
  );
}

// -------------------------------------------------------------- sidebar

function BrandMark({ collapsed }: { collapsed: boolean }) {
  return (
    <div className="flex min-w-0 items-center gap-2.5">
      <span
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-console"
        style={{
          background: "var(--color-accent)",
          color: "var(--color-accent-ink)",
          boxShadow: "0 8px 22px -12px var(--color-accent)",
        }}
      >
        <Activity size={17} strokeWidth={2.4} />
      </span>
      {collapsed ? null : (
        <span className="min-w-0">
          <span className="block truncate font-mono text-[12px] font-semibold tracking-[0.22em] text-heading">
            DIGDEEPER
          </span>
          <span className="block truncate text-[10px] tracking-[0.02em] text-ink-faint">
            Dig without leaving the room
          </span>
        </span>
      )}
    </div>
  );
}

export function Sidebar() {
  const collapsed = useShellStore((s) => s.collapsed);
  const setCollapsed = useShellStore((s) => s.setCollapsed);
  const crateCount = useCrateStore((s) => s.tracks.length);
  const openCrate = useCrateStore((s) => s.setOpen);
  const width = collapsed ? 64 : 224;

  return (
    <aside
      aria-label="Primary"
      className="fixed left-0 bottom-[84px] top-0 z-30 hidden flex-col border-r border-line lg:flex"
      style={{
        width,
        background:
          "linear-gradient(180deg, rgba(10, 10, 12, 0.94) 0%, rgba(5, 5, 6, 0.97) 100%)",
        backdropFilter: "blur(24px) saturate(140%)",
        WebkitBackdropFilter: "blur(24px) saturate(140%)",
      }}
    >
      <div className="flex items-center justify-between gap-1 border-b border-line px-2 py-3">
        <BrandMark collapsed={collapsed} />
        <button
          type="button"
          onClick={() => setCollapsed(!collapsed)}
          className="btn btn-ghost !min-h-0 shrink-0 !border-0 !bg-transparent p-2 text-ink-faint hover:text-heading"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-pressed={collapsed}
        >
          {collapsed ? <PanelLeftOpen size={15} /> : <PanelLeftClose size={15} />}
        </button>
      </div>

      <nav className="mt-3 flex flex-1 flex-col gap-0.5 px-2">
        <p className="px-2 pb-2 font-mono text-[8px] uppercase tracking-[0.2em] text-ink-faint">
          {collapsed ? "—" : "Workspaces"}
        </p>
        {NAV_ITEMS.map((item, i) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              role="tab"
              data-tab-label={item.label}
              className={({ isActive }) =>
                `nav-item ${isActive ? "!text-heading" : ""}`
              }
              title={collapsed ? item.label : undefined}
            >
              {({ isActive }) => (
                <>
                  <span
                    className={`font-num w-4 shrink-0 text-[9px] ${
                      isActive ? "text-accent" : "text-ink-faint"
                    }`}
                    aria-hidden
                  >
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <Icon
                    size={15}
                    className={`shrink-0 ${isActive ? "text-accent" : ""}`}
                  />
                  {collapsed ? (
                    <span className="sr-only">{item.label}</span>
                  ) : (
                    <span className="flex-1 truncate">{item.label}</span>
                  )}
                </>
              )}
            </NavLink>
          );
        })}
      </nav>

      <div className="border-t border-line px-2 pt-3 pb-2">
        {collapsed ? null : (
          <p className="px-2 pb-2 font-mono text-[8px] uppercase tracking-[0.2em] text-ink-faint">
            Pinned
          </p>
        )}
        <button
          type="button"
          onClick={() => openCrate(true)}
          className="nav-item w-full justify-start"
          title="Open the Set Crate"
        >
          <ListMusic size={15} className="shrink-0" />
          {collapsed ? (
            <span className="sr-only">Active Set Crate</span>
          ) : (
            <span className="flex-1 truncate text-left">Active Set Crate</span>
          )}
          {crateCount > 0 ? (
            <span
              className="font-num flex h-5 min-w-5 items-center justify-center rounded-pill px-1.5 text-[10px] font-semibold text-accent-ink"
              style={{ background: "var(--color-accent)" }}
            >
              {crateCount}
            </span>
          ) : null}
        </button>
        <NavLink
          to="/builder"
          className="nav-item mt-0.5 w-full justify-start"
          title="Saved Sets in the Set Builder"
        >
          <ChevronRight size={15} className="shrink-0" />
          {collapsed ? (
            <span className="sr-only">Saved Sets</span>
          ) : (
            <span className="flex-1 truncate">Saved Sets</span>
          )}
        </NavLink>
      </div>

      <div className="px-2 pb-3">
        {collapsed ? (
          <div className="flex justify-center py-2">
            <ApiStatus compact />
          </div>
        ) : (
          <ApiStatus />
        )}
      </div>
    </aside>
  );
}

// -------------------------------------------------------- utility strip

export function UtilityStrip() {
  const { pathname } = useLocation();
  const current =
    NAV_ITEMS.find((item) => item.to !== "/" && pathname.startsWith(item.to)) ??
    NAV_ITEMS[0];
  const crateCount = useCrateStore((s) => s.tracks.length);
  const toggleCrate = useCrateStore((s) => s.toggle);

  return (
    <div
      className="sticky top-0 z-20 hidden h-11 items-center justify-between gap-3 border-b border-line px-6 lg:flex"
      style={{
        background: "rgba(0, 0, 0, 0.68)",
        backdropFilter: "blur(24px) saturate(150%)",
        WebkitBackdropFilter: "blur(24px) saturate(150%)",
      }}
    >
      <p className="font-mono text-[9px] uppercase tracking-[0.16em] text-ink-faint">
        DigDeeper <span className="mx-2 text-line-strong">/</span>
        <span className="text-ink">{current.label}</span>
      </p>
      <div className="flex items-center gap-3">
        <ApiStatus compact />
        <button
          type="button"
          onClick={toggleCrate}
          className="inline-flex min-h-7 items-center gap-1.5 rounded-pill border border-line px-3 py-1 font-mono text-[9px] uppercase tracking-[0.14em] text-ink-dim transition-colors hover:border-line-strong hover:text-heading"
        >
          <ListMusic size={12} />
          Crate
          <span className="font-num text-[10px] text-heading">{crateCount}</span>
        </button>
      </div>
    </div>
  );
}
