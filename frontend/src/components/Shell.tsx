import {
  Gauge,
  Disc3,
  ListOrdered,
  AudioWaveform,
  Library,
  Workflow,
  Activity,
} from "lucide-react";
import { NavLink, useLocation } from "react-router-dom";
import { api } from "../api/client";
import { useEffect, useState } from "react";
import type { HardwareResponse } from "../types/apiTypes";

const TABS = [
  { to: "/", label: "DASHBOARD", icon: Gauge, end: true },
  { to: "/dig", label: "DIG", icon: Disc3 },
  { to: "/builder", label: "SET BUILDER", icon: ListOrdered },
  { to: "/mix", label: "MIX ANALYZER", icon: AudioWaveform },
  { to: "/library", label: "LIBRARY", icon: Library },
  { to: "/pipeline", label: "PIPELINE", icon: Workflow },
];

export function TopBar() {
  const { pathname } = useLocation();

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-canvas/95 backdrop-blur">
      <div className="flex items-center justify-between gap-4 px-4 pt-2 sm:px-6">
        <p className="eyebrow !text-ink-dim">DIGDEEPER — SET COMMAND CENTER</p>
        <span className="hidden font-num text-[10px] uppercase tracking-[0.14em] text-ink-faint md:block">
          100% LOCAL
        </span>
      </div>
      <nav
        aria-label="Workspaces"
        className="scroll-thin flex items-end gap-5 overflow-x-auto px-4 sm:px-6"
      >
        {TABS.map(({ to, label, icon: Icon, end }) => {
          const active = end ? pathname === to : pathname.startsWith(to);
          return (
            <NavLink
              key={to}
              to={to}
              end={end}
              role="tab"
              aria-selected={active}
              data-tab-label={label}
              className="tab shrink-0"
            >
              <Icon size={13} className="mr-1.5 inline-block" aria-hidden />
              {label}
            </NavLink>
          );
        })}
      </nav>
    </header>
  );
}

export function ApiStatusDot() {
  const [hw, setHw] = useState<HardwareResponse | null>(null);
  const [online, setOnline] = useState<boolean | null>(null);

  useEffect(() => {
    let alive = true;
    const probe = () => {
      api
        .hardware()
        .then((res) => {
          if (!alive) return;
          setHw(res);
          setOnline(true);
        })
        .catch(() => {
          if (!alive) return;
          setOnline(false);
        });
    };
    probe();
    const timer = window.setInterval(probe, 30000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, []);

  const color =
    online == null
      ? "var(--color-ink-faint)"
      : online
        ? "var(--color-accent)"
        : "var(--color-danger)";

  return (
    <div
      className="flex items-center gap-2 px-1 py-2"
      data-testid="api-status"
      aria-live="polite"
    >
      <span
        aria-hidden
        className="inline-block h-2 w-2 rounded-full"
        style={{ background: color }}
      />
      <span className="font-num text-[10px] uppercase tracking-[0.12em] text-ink-faint">
        {online == null ? "CHECKING" : online ? "API ONLINE" : "API OFFLINE"}
      </span>
      {hw?.gpu_name ? (
        <span className="hidden font-num text-[10px] text-ink-faint xl:inline">
          · {hw.gpu_name}
        </span>
      ) : null}
    </div>
  );
}

/** Left rail (desktop only): brand mark + live API status. */
export function IconRail() {
  return (
    <aside className="fixed inset-y-0 left-0 z-30 hidden w-[56px] flex-col items-center justify-between border-r border-line bg-panel py-4 lg:flex">
      <Activity size={18} className="text-accent" aria-hidden />
      <ApiStatusDot />
    </aside>
  );
}
