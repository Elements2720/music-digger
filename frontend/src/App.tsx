import { useEffect } from "react";
import type { CSSProperties } from "react";
import { Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { Sidebar, UtilityStrip, useShellStore } from "./components/Shell";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { MobileChrome } from "./components/MobileChrome";
import { PlayerDock } from "./components/PlayerDock";
import { SetCrateDrawer } from "./components/SetCrateDrawer";
import { DashboardView } from "./views/Dashboard";
import { DigView } from "./views/Dig";
import { BuilderView } from "./views/Builder";
import { MixView } from "./views/Mix";
import { LibraryView } from "./views/Library";
import { PipelineView } from "./views/Pipeline";
import { SettingsView } from "./views/Settings";
import { useJobsStore } from "./stores/jobsStore";
import { usePlayerStore } from "./stores/playerStore";
import { useCrateStore } from "./stores/crateStore";
import { useSettingsStore } from "./stores/settingsStore";

function isTypingTarget(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false;
  return (
    el.tagName === "INPUT" ||
    el.tagName === "TEXTAREA" ||
    el.tagName === "SELECT" ||
    el.isContentEditable
  );
}

function KeyboardShortcuts() {
  const navigate = useNavigate();
  const { toggle, nudge, current } = usePlayerStore();
  const toggleCrate = useCrateStore((s) => s.toggle);
  const enabled = useSettingsStore((s) => s.keyboardShortcutsEnabled);
  const seekStepSec = useSettingsStore((s) => s.seekStepSec);

  useEffect(() => {
    if (!enabled) return undefined;
    const onKey = (e: KeyboardEvent) => {
      if (isTypingTarget(e.target) || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === " ") {
        e.preventDefault();
        if (current) toggle();
      } else if (e.key === "m" || e.key === "M") {
        if (current) usePlayerStore.getState().toggleMute();
      } else if (e.key === "ArrowRight" && e.shiftKey) {
        navigate("/pipeline");
      } else if (e.key === "ArrowLeft" && e.shiftKey) {
        navigate("/");
      } else if (e.key === "ArrowRight" && !e.shiftKey && current) {
        e.preventDefault();
        nudge(seekStepSec);
      } else if (e.key === "ArrowLeft" && !e.shiftKey && current) {
        e.preventDefault();
        nudge(-seekStepSec);
      } else if (e.key === "c" || e.key === "C") {
        toggleCrate();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [enabled, seekStepSec, navigate, toggle, nudge, current, toggleCrate]);

  return null;
}

function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return null;
}

export function App() {
  const connect = useJobsStore((s) => s.connect);
  const refreshJobs = useJobsStore((s) => s.refresh);
  const collapsed = useShellStore((s) => s.collapsed);
  const accentTheme = useSettingsStore((s) => s.accentTheme);
  const ambientGlow = useSettingsStore((s) => s.ambientGlow);
  const rowDensity = useSettingsStore((s) => s.rowDensity);

  useEffect(() => {
    const root = document.documentElement;
    root.dataset.accent = accentTheme;
    root.dataset.glow = ambientGlow ? "on" : "off";
    root.dataset.density = rowDensity;
  }, [accentTheme, ambientGlow, rowDensity]);

  useEffect(() => {
    if (useSettingsStore.getState().defaultCrateOpen) {
      useCrateStore.getState().setOpen(true);
    }
  }, []);

  useEffect(() => {
    const close = connect();
    void refreshJobs();
    return close;
  }, [connect, refreshJobs]);

  return (
    <div
      className="app-shell min-h-full"
      style={{ "--shell-w": collapsed ? "64px" : "224px" } as CSSProperties}
    >
      <KeyboardShortcuts />
      <ScrollToTop />
      <Sidebar />
      <MobileChrome />
      <div className="flex min-h-full flex-col">
        <UtilityStrip />
        <main className="mx-auto w-full max-w-[1440px] px-4 pb-[164px] pt-20 sm:px-6 lg:pb-32 lg:pt-5">
          <ErrorBoundary>
            <Routes>
              <Route path="/" element={<DashboardView />} />
              <Route path="/dig" element={<DigView />} />
              <Route path="/builder" element={<BuilderView />} />
              <Route path="/mix" element={<MixView />} />
              <Route path="/library" element={<LibraryView />} />
              <Route path="/pipeline" element={<PipelineView />} />
              <Route path="/settings" element={<SettingsView />} />
              <Route path="*" element={<DashboardView />} />
            </Routes>
          </ErrorBoundary>
        </main>
      </div>
      <SetCrateDrawer />
      <PlayerDock />
    </div>
  );
}
