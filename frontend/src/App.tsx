import { useEffect } from "react";
import { Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { TopBar, IconRail } from "./components/Shell";
import { PlayerDock } from "./components/PlayerDock";
import { SetCrateDrawer } from "./components/SetCrateDrawer";
import { DashboardView } from "./views/Dashboard";
import { DigView } from "./views/Dig";
import { BuilderView } from "./views/Builder";
import { MixView } from "./views/Mix";
import { LibraryView } from "./views/Library";
import { PipelineView } from "./views/Pipeline";
import { useJobsStore } from "./stores/jobsStore";
import { usePlayerStore } from "./stores/playerStore";
import { useCrateStore } from "./stores/crateStore";

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

  useEffect(() => {
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
      } else if (e.key === "c" || e.key === "C") {
        toggleCrate();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navigate, toggle, nudge, current, toggleCrate]);

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

  useEffect(() => {
    const close = connect();
    void refreshJobs();
    return close;
  }, [connect, refreshJobs]);

  return (
    <div className="min-h-full lg:pl-[56px]">
      <KeyboardShortcuts />
      <ScrollToTop />
      <TopBar />
      <main className="mx-auto w-full max-w-[1440px] px-4 pb-28 pt-4 sm:px-6">
        <Routes>
          <Route path="/" element={<DashboardView />} />
          <Route path="/dig" element={<DigView />} />
          <Route path="/builder" element={<BuilderView />} />
          <Route path="/mix" element={<MixView />} />
          <Route path="/library" element={<LibraryView />} />
          <Route path="/pipeline" element={<PipelineView />} />
          <Route path="*" element={<DashboardView />} />
        </Routes>
      </main>
      <SetCrateDrawer />
      <PlayerDock />
      <IconRail />
    </div>
  );
}
