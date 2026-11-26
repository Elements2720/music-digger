import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import {
  ArrowDown,
  ArrowUp,
  ChevronDown,
  Download,
  FileDown,
  Plus,
  Save,
  Search,
  Sparkles,
  Trash2,
  Wand2,
} from "lucide-react";
import { api } from "../api/client";
import { useSettingsStore } from "../stores/settingsStore";
import { buildM3u8, downloadPlaylist, remapM3u8 } from "../lib/m3u8";
import type {
  BridgeSuggestion,
  EvaluateSequenceResponse,
  NextTrackSuggestion,
  PlannedSet,
  Track,
  TransitionEvaluation,
} from "../types/apiTypes";
import {
  ConfirmActionButton,
  EmptyState,
  ErrorState,
  Loading,
  PanelHead,
  TrackRow,
} from "../components/ui";
import { useCrateStore } from "../stores/crateStore";
import { useJobsStore } from "../stores/jobsStore";
import { fmtBpm, fmtClock, fmtPercent } from "../lib/format";

const FLOWS = [
  { id: "steady", label: "Steady", hint: "Locks BPM, calm energy" },
  { id: "ramp_up", label: "Ramp Up (+2)", hint: "Builds energy across the set" },
  { id: "cool_down", label: "Cool Down (-2)", hint: "Eases the energy down" },
  { id: "any", label: "Any", hint: "Best score regardless of direction" },
] as const;
type Flow = (typeof FLOWS)[number]["id"];

const MOVE_LABEL: Record<string, string> = {
  same: "Same Key",
  relative: "Relative",
  "+1": "Smooth +1",
  "-1": "Smooth -1",
  "+2": "Boost +2",
  "-2": "Boost -2",
  "+7": "Jump +7",
  "-7": "Jump -7",
  "0": "Same Key",
  unknown: "Unknown key",
};

function moveLabel(move: string | null | undefined): string {
  if (!move) return "—";
  return MOVE_LABEL[move] ?? move;
}

function signedBpm(delta: number | null | undefined): string | null {
  if (delta == null || !Number.isFinite(delta)) return null;
  const rounded = Math.round(delta * 10) / 10;
  return `${rounded > 0 ? "+" : ""}${rounded.toFixed(1)} BPM`;
}

function flowLabel(flow: Flow): string {
  return FLOWS.find((f) => f.id === flow)?.label ?? "Any";
}

function activeSetFlow() {
  const settings = useSettingsStore.getState();
  return {
    pathMode: settings.m3u8PathMode,
    pathPrefix: settings.m3u8PathPrefix,
    includeMetadata: settings.m3u8IncludeMetadata,
  };
}

function transitionText(t: TransitionEvaluation | null | undefined): string | null {
  if (!t) return null;
  const parts = [moveLabel(t.camelot_move)];
  const delta = signedBpm(t.bpm_delta);
  if (delta) parts.push(delta);
  return parts.join(" · ");
}

// ------------------------------------------------ progression chart

function ProgressionChart({ tracks }: { tracks: Track[] }) {
  const w = 600;
  const h = 96;
  const padX = 34;
  const padY = 20;
  const raw = tracks.map((t) =>
    typeof t.bpm === "number" && Number.isFinite(t.bpm) ? t.bpm : null,
  );
  const known = raw.filter((b): b is number => b != null);
  const min = known.length ? Math.min(...known) : 0;
  const max = known.length ? Math.max(...known) : 0;
  const span = Math.max(1, max - min);
  const plotW = w - padX * 2;
  const plotH = h - padY * 2;
  const stepX = tracks.length > 1 ? plotW / (tracks.length - 1) : 0;
  let lastKnown = min;
  const points = raw.map((bpm, idx) => {
    const value = bpm ?? lastKnown;
    lastKnown = value;
    const x = padX + idx * stepX;
    const y = padY + plotH - ((value - min) / span) * plotH;
    return { x, y, bpm: value };
  });
  const line = points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  const area =
    points.length > 0
      ? `${points[0].x.toFixed(1)},${h} ${line} ${points[points.length - 1].x.toFixed(1)},${h}`
      : "";

  if (tracks.length < 2 || known.length === 0) {
    return (
      <div className="flex h-24 items-center justify-center border-b border-line px-3">
        <p className="text-center text-[11px] text-ink-faint">
          Add 2+ tracks with BPM data to see the BPM and energy progression.
        </p>
      </div>
    );
  }

  return (
    <div className="border-b border-line px-2 pb-1 pt-2">
      <svg
        viewBox={`0 0 ${w} ${h}`}
        className="h-24 w-full"
        role="img"
        aria-label={`BPM progression across ${tracks.length} tracks, ${min.toFixed(1)} to ${max.toFixed(1)} BPM`}
      >
        <defs>
          <linearGradient id="progression-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--color-accent)" stopOpacity="0.22" />
            <stop offset="100%" stopColor="var(--color-accent)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <polygon points={area} fill="url(#progression-fill)" />
        <polyline
          points={line}
          fill="none"
          stroke="var(--color-accent)"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {points.map((p, i) => {
          const key = tracks[i]?.key;
          return (
            <g key={i}>
              <circle
                cx={p.x}
                cy={p.y}
                r="4.5"
                fill="#0b0b0c"
                stroke="var(--color-accent)"
                strokeWidth="2"
              />
              <text
                x={p.x}
                y={p.y - 8}
                textAnchor="middle"
                fill="#a1a1aa"
                fontSize="9"
                fontFamily="var(--font-mono)"
              >
                {Math.round(p.bpm)}
              </text>
              {key ? (
                <text
                  x={p.x}
                  y={p.y + 16}
                  textAnchor="middle"
                  fill="var(--color-accent)"
                  fontSize="9"
                  fontFamily="var(--font-mono)"
                >
                  {key}
                </text>
              ) : null}
            </g>
          );
        })}
      </svg>
      <div className="flex items-center justify-between border-t border-line px-2 pt-1.5 font-mono text-[9px] uppercase tracking-[0.12em] text-ink-faint">
        <span>BPM progression</span>
        <span className="text-ink-dim">
          {min === max
            ? `${min.toFixed(1)} BPM`
            : `${min.toFixed(1)} – ${max.toFixed(1)} BPM`}
        </span>
      </div>
    </div>
  );
}

// ------------------------------------------------ builder view

export function BuilderView() {
  const crate = useCrateStore((s) => s.tracks);
  const replaceAll = useCrateStore((s) => s.replaceAll);
  const clearCrate = useCrateStore((s) => s.clear);
  const addToCrate = useCrateStore((s) => s.add);
  const startJob = useJobsStore((s) => s.start);
  const [flow, setFlow] = useState<Flow>("ramp_up");
  const [evaluation, setEvaluation] = useState<EvaluateSequenceResponse | null>(null);
  const [saved, setSaved] = useState<PlannedSet[]>([]);
  const [name, setName] = useState("");
  const [loadedSetId, setLoadedSetId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [tab, setTab] = useState<"next" | "bridge">("next");
  const [sequenceOpen, setSequenceOpen] = useState(false);
  const sequenceRef = useRef<HTMLDivElement | null>(null);

  const [referenceId, setReferenceId] = useState("");
  const [localOnly, setLocalOnly] = useState(false);
  const [suggestions, setSuggestions] = useState<NextTrackSuggestion[] | null>(null);
  const [bridgeA, setBridgeA] = useState("");
  const [bridgeB, setBridgeB] = useState("");
  const [bridges, setBridges] = useState<BridgeSuggestion[] | null>(null);
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<Track[] | null>(null);
  const [searching, setSearching] = useState(false);

  const { hash } = useLocation();
  const [savedLoading, setSavedLoading] = useState(false);

  const refreshSaved = () => {
    setSavedLoading(true);
    api
      .listPlannedSets()
      .then(setSaved)
      .catch(() => undefined)
      .finally(() => setSavedLoading(false));
  };

  useEffect(refreshSaved, []);

  useEffect(() => {
    if (hash === "#saved") {
      document.getElementById("saved")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [hash, saved.length]);

  useEffect(() => {
    if (crate.length === 0) {
      if (referenceId) setReferenceId("");
      if (bridgeA) setBridgeA("");
      if (bridgeB) setBridgeB("");
      return;
    }
    if (!crate.some((t) => t.id === referenceId)) setReferenceId(crate[crate.length - 1].id);
    if (!crate.some((t) => t.id === bridgeA)) setBridgeA(crate[0].id);
    if (!crate.some((t) => t.id === bridgeB)) setBridgeB(crate[crate.length - 1].id);
  }, [crate, referenceId, bridgeA, bridgeB]);

  useEffect(() => {
    if (!sequenceOpen) return;
    const onClick = (event: MouseEvent) => {
      if (!sequenceRef.current?.contains(event.target as Node)) setSequenceOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSequenceOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      window.removeEventListener("keydown", onKey);
    };
  }, [sequenceOpen]);

  const totalSeconds = crate.reduce((acc, t) => acc + (t.duration_seconds ?? 0), 0);
  const missingLocal = useMemo(() => crate.filter((t) => !t.has_local_file), [crate]);
  const crateKey = crate.map((t) => t.id).join("|");

  useEffect(() => {
    if (crate.length < 2) {
      setEvaluation(null);
      return;
    }
    let alive = true;
    const timer = window.setTimeout(() => {
      api
        .evaluate({ track_ids: crate.map((t) => t.id), flow })
        .then((res) => alive && setEvaluation(res))
        .catch(() => alive && setEvaluation(null));
    }, 350);
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [crateKey, flow]);

  const autoSequence = async (selectedFlow: Flow = flow) => {
    if (crate.length < 2) return;
    setBusy(true);
    setError(null);
    setSequenceOpen(false);
    try {
      const res = await api.autoSequence({
        track_ids: crate.map((t) => t.id),
        flow: selectedFlow,
        lock_first: true,
      });
      const byId = new Map(crate.map((t) => [t.id, t]));
      const ordered = res.ordered_track_ids
        .map((id) => byId.get(id))
        .filter((t): t is NonNullable<typeof t> => Boolean(t));
      replaceAll(ordered);
      setStatus(
        `Sequenced ${ordered.length} tracks (${flowLabel(selectedFlow)}, avg score ${fmtPercent(res.average_score * 100)})`,
      );
    } catch (err) {
      if (err instanceof Error) setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const saveSet = async () => {
    if (crate.length === 0) return;
    const trimmed = name.trim();
    const label = trimmed || `${new Date().toISOString().slice(0, 10)} — ${crate.length} tracks`;
    setBusy(true);
    setError(null);
    try {
      const trackIds = crate.map((t) => t.id);
      if (loadedSetId != null) {
        await api.updatePlannedSet(loadedSetId, { name: label, track_ids: trackIds });
        setStatus(`Updated "${label}"`);
      } else {
        const created = await api.createPlannedSet({ name: label, track_ids: trackIds });
        setLoadedSetId(created.id);
        setStatus(`Saved "${created.name}"`);
      }
      setName(label);
      refreshSaved();
    } catch (err) {
      if (err instanceof Error) setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const exportM3u8 = async (id: number) => {
    try {
      const text = remapM3u8(await api.exportPlannedSetM3u8(id), activeSetFlow());
      downloadPlaylist(`set-${id}.m3u8`, text);
      setStatus("Playlist exported (.m3u8)");
    } catch (err) {
      if (err instanceof Error) setError(err.message);
    }
  };

  const exportCrate = () => {
    const { text, skipped } = buildM3u8(crate, activeSetFlow());
    downloadPlaylist(name.trim() || "crate", text);
    setStatus(
      skipped > 0
        ? `Playlist exported — ${skipped} track(s) without a local file were skipped`
        : "Playlist exported (.m3u8)",
    );
  };

  const downloadMissing = async () => {
    if (missingLocal.length === 0) return;
    setError(null);
    try {
      await startJob("download-tracks", {
        track_ids: missingLocal.map((t) => t.id),
        skip_existing: true,
      });
      setStatus(`Downloading ${missingLocal.length} missing track(s) — see Pipeline`);
    } catch (err) {
      if (err instanceof Error) setError(err.message);
    }
  };

  const suggest = async () => {
    if (!referenceId) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.suggestNext({
        from_track_id: referenceId,
        flow,
        local_only: localOnly,
        limit: 8,
      });
      setSuggestions(res.suggestions);
    } catch (err) {
      if (err instanceof Error) setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (!referenceId || tab !== "next") return;
    let alive = true;
    const timer = window.setTimeout(() => {
      api
        .suggestNext({
          from_track_id: referenceId,
          flow,
          local_only: localOnly,
          limit: 8,
        })
        .then((res) => alive && setSuggestions(res.suggestions))
        .catch(() => alive && setSuggestions([]));
    }, 300);
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [referenceId, flow, localOnly, tab]);

  const findBridge = async () => {
    if (!bridgeA || !bridgeB || bridgeA === bridgeB) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.bridge({
        track_a_id: bridgeA,
        track_b_id: bridgeB,
        local_only: localOnly,
        limit: 6,
      });
      setBridges(res.bridges);
    } catch (err) {
      if (err instanceof Error) setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const bridgeBetween = async (index: number) => {
    const a = crate[index];
    const b = crate[index + 1];
    if (!a || !b) return;
    setBridgeA(a.id);
    setBridgeB(b.id);
    setTab("bridge");
    setBusy(true);
    setError(null);
    try {
      const res = await api.bridge({
        track_a_id: a.id,
        track_b_id: b.id,
        local_only: localOnly,
        limit: 6,
      });
      setBridges(res.bridges);
      setStatus(`Bridge options for ${a.title} → ${b.title}`);
    } catch (err) {
      if (err instanceof Error) setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const search = async () => {
    if (!query.trim()) return;
    setSearching(true);
    try {
      const res = await api.searchTracks(query.trim(), 10);
      setSearchResults(res.tracks);
    } catch (err) {
      if (err instanceof Error) setError(err.message);
    } finally {
      setSearching(false);
    }
  };

  const loadSet = async (s: PlannedSet) => {
    try {
      const detail = await api.getPlannedSet(s.id);
      replaceAll(detail.tracks ?? []);
      setLoadedSetId(detail.id);
      setName(detail.name);
      setStatus(`Loaded "${detail.name}" into the crate`);
    } catch (err) {
      if (err instanceof Error) setError(err.message);
    }
  };

  const deleteSet = async (id: number) => {
    try {
      await api.deletePlannedSet(id);
      if (loadedSetId === id) setLoadedSetId(null);
      refreshSaved();
    } catch (err) {
      if (err instanceof Error) setError(err.message);
    }
  };

  const move = (index: number, dir: -1 | 1) => {
    const to = index + dir;
    if (to < 0 || to >= crate.length) return;
    useCrateStore.getState().move(crate[index].id, to);
  };

  const transitions = evaluation?.transitions ?? [];
  const avgFlow =
    transitions.length > 0
      ? fmtPercent(
          transitions.reduce((acc, t) => acc + t.score, 0) / transitions.length,
        )
      : null;
  const referenceIndex = crate.findIndex((t) => t.id === referenceId);
  const reference = referenceIndex >= 0 ? crate[referenceIndex] : null;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h1 className="text-2xl font-bold tracking-[-0.02em] text-heading">Set Builder</h1>
        <span className="font-num text-xs text-ink-dim">
          {crate.length} TRACKS · {fmtClock(totalSeconds)}
        </span>
      </div>

      {error ? (
        <ErrorState
          message={error}
          onRetry={() => {
            setError(null);
            refreshSaved();
          }}
        />
      ) : null}
      {status ? (
        <p className="font-mono text-xs text-accent" role="status">
          {status}
        </p>
      ) : null}

      <div className="panel flex flex-wrap items-center gap-2 p-3">
        <input
          className="input min-w-[160px] flex-1"
          placeholder="My DJ Set Plan"
          value={name}
          onChange={(e) => setName(e.target.value)}
          aria-label="Set name"
        />
        <select
          className="input !w-auto max-w-[220px]"
          value={loadedSetId ?? ""}
          onChange={(e) => {
            const id = Number(e.target.value);
            const match = saved.find((s) => s.id === id);
            if (match) void loadSet(match);
          }}
          aria-label="Load saved set"
        >
          <option value="">-- Load Saved Set --</option>
          {saved.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => void saveSet()}
          disabled={busy || crate.length === 0}
        >
          <Save size={14} /> {loadedSetId != null ? "UPDATE SET" : "SAVE SET"}
        </button>
        <div className="relative" ref={sequenceRef}>
          <button
            type="button"
            className="btn"
            aria-haspopup="menu"
            aria-expanded={sequenceOpen}
            onClick={() => setSequenceOpen((v) => !v)}
            disabled={busy || crate.length < 2}
          >
            <Wand2 size={14} /> AUTO-SEQUENCE <ChevronDown size={13} />
          </button>
          {sequenceOpen ? (
            <div
              role="menu"
              className="panel absolute right-0 z-30 mt-1 w-[220px] overflow-hidden p-1"
            >
              {FLOWS.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  role="menuitem"
                  className="flex w-full flex-col items-start gap-0.5 rounded-sm px-2.5 py-2 text-left hover:bg-fill"
                  onClick={() => void autoSequence(f.id)}
                >
                  <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-heading">
                    {f.label}
                  </span>
                  <span className="text-[10px] text-ink-faint">{f.hint}</span>
                </button>
              ))}
            </div>
          ) : null}
        </div>
        <button
          type="button"
          className="btn"
          onClick={() =>
            loadedSetId != null ? void exportM3u8(loadedSetId) : exportCrate()
          }
          disabled={crate.length === 0}
        >
          <FileDown size={14} /> EXPORT .M3U8
        </button>
        <button
          type="button"
          className="btn"
          onClick={() => void downloadMissing()}
          disabled={missingLocal.length === 0}
          title="Download previews for tracks that have no local file"
        >
          <Download size={14} /> DOWNLOAD MISSING
          {missingLocal.length ? ` (${missingLocal.length})` : ""}
        </button>
        <ConfirmActionButton
          onConfirm={() => {
            clearCrate();
            setLoadedSetId(null);
            setName("");
            setEvaluation(null);
            setStatus("Crate cleared");
          }}
          label={
            <>
              <Trash2 size={14} /> CLEAR
            </>
          }
          confirmLabel="CONFIRM CLEAR?"
          className="btn btn-danger"
          disabled={crate.length === 0}
          ariaLabel="Clear crate and reset active set"
          confirmAriaLabel="Confirm clearing crate"
        />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <section className="panel min-w-0 self-start" aria-label="Set tracklist">
          <PanelHead
            title="SET TRACKLIST"
            right={
              <span className="flex flex-wrap items-center gap-2">
                <span className="font-num text-[11px] text-ink-dim">
                  {crate.length} tracks · {fmtClock(totalSeconds)}
                </span>
                {avgFlow ? (
                  <span className="pill border-accent/40 font-num uppercase text-accent">
                    Avg Flow: {avgFlow}
                  </span>
                ) : null}
              </span>
            }
          />
          <ProgressionChart tracks={crate} />
          {crate.length === 0 ? (
            <EmptyState
              title="CRATE EMPTY"
              hint="Add tracks from Dashboard, Dig or Library with the + Set action, then sequence and save them here."
            />
          ) : (
            <div>
              {crate.map((t, i) => {
                const transition = evaluation?.transitions?.[i] ?? null;
                const next = crate[i + 1];
                return (
                  <div key={t.id} className="flex flex-col">
                    <TrackRow
                      track={t}
                      queue={crate}
                      index={i}
                      trailing={
                        <span className="flex gap-1">
                          <button
                            type="button"
                            className="btn btn-ghost !min-h-0 p-1.5"
                            onClick={() => move(i, -1)}
                            disabled={i === 0}
                            aria-label={`Move ${t.title} up`}
                          >
                            <ArrowUp size={13} />
                          </button>
                          <button
                            type="button"
                            className="btn btn-ghost !min-h-0 p-1.5"
                            onClick={() => move(i, 1)}
                            disabled={i === crate.length - 1}
                            aria-label={`Move ${t.title} down`}
                          >
                            <ArrowDown size={13} />
                          </button>
                          <button
                            type="button"
                            className="btn btn-ghost !min-h-0 p-1.5 text-danger"
                            onClick={() => useCrateStore.getState().remove(t.id)}
                            aria-label={`Remove ${t.title} from the crate`}
                          >
                            <Trash2 size={13} />
                          </button>
                        </span>
                      }
                    />
                    {next ? (
                      <div className="flex flex-wrap items-center gap-2 border-b border-line bg-panel-2/40 px-3 py-1.5">
                        <span
                          className="font-num text-[10px]"
                          style={{
                            color:
                              transition == null
                                ? "var(--color-ink-faint)"
                                : transition.score >= 66
                                  ? "var(--color-accent)"
                                  : transition.score >= 33
                                    ? "var(--color-warn)"
                                    : "var(--color-danger)",
                          }}
                        >
                          {transition ? `${Math.round(transition.score)}%` : "—"}
                        </span>
                        <span className="font-num min-w-0 truncate text-[10px] text-ink-dim">
                          {transition
                            ? `${moveLabel(transition.camelot_move)} (${t.key ?? "—"} → ${next.key ?? "—"})`
                            : `Transition ${t.key ?? "—"} → ${next.key ?? "—"}`}
                          {transition && signedBpm(transition.bpm_delta)
                            ? ` · ${signedBpm(transition.bpm_delta)}`
                            : ""}
                        </span>
                        <span className="hidden h-1 min-w-[40px] flex-1 overflow-hidden rounded bg-white/[0.05] sm:block">
                          <span
                            className="block h-full rounded"
                            style={{
                              width: `${transition ? Math.max(2, Math.min(100, transition.score)) : 0}%`,
                              background:
                                transition == null
                                  ? "var(--color-line-strong)"
                                  : transition.score >= 66
                                    ? "var(--color-accent)"
                                    : transition.score >= 33
                                      ? "var(--color-warn)"
                                      : "var(--color-danger)",
                            }}
                          />
                        </span>
                        <button
                          type="button"
                          className="btn btn-ghost !min-h-7 px-2.5 py-1 font-mono text-[9px]"
                          onClick={() => void bridgeBetween(i)}
                          title={`Find a bridge between ${t.title} and ${next.title}`}
                        >
                          <Plus size={11} /> BRIDGE
                        </button>
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          )}
        </section>

        <section className="panel min-w-0 self-start" aria-label="Set helper">
          <div className="panel-head !items-center">
            <div className="flex items-center gap-5" role="tablist" aria-label="Set helper modes">
              <button
                type="button"
                role="tab"
                aria-selected={tab === "next"}
                className="tab !min-h-10"
                onClick={() => setTab("next")}
              >
                NEXT TRACK
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={tab === "bridge"}
                className="tab !min-h-10"
                onClick={() => setTab("bridge")}
              >
                FIND BRIDGE
              </button>
            </div>
            <label className="flex min-h-8 items-center gap-2 font-mono text-[10px] uppercase text-ink-dim">
              <input
                type="checkbox"
                checked={localOnly}
                onChange={(e) => setLocalOnly(e.target.checked)}
                className="h-3.5 w-3.5 accent-accent"
              />
              LOCAL FILES ONLY
            </label>
          </div>
          <div className="flex flex-wrap gap-1.5 border-b border-line px-3 py-2">
            {FLOWS.map((f) => (
              <button
                key={f.id}
                type="button"
                aria-pressed={flow === f.id}
                className={`rounded-pill border px-2.5 py-1 font-mono text-[10px] transition-colors ${
                  flow === f.id
                    ? "border-accent/60 bg-accent/15 text-accent"
                    : "border-line text-ink-dim hover:border-white/25 hover:text-heading"
                }`}
                onClick={() => setFlow(f.id)}
                title={f.hint}
              >
                {f.label}
              </button>
            ))}
          </div>
          <form
            className="flex gap-2 border-b border-line px-3 py-2"
            onSubmit={(e) => {
              e.preventDefault();
              void search();
            }}
          >
            <div className="input-icon-wrap min-w-0 flex-1">
              <Search
                size={13}
                aria-hidden
              />
              <input
                className="input !min-h-0 py-2 text-xs"
                placeholder="Search catalog to add…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                aria-label="Search the catalog"
              />
            </div>
            <button
              type="submit"
              className="btn btn-ghost !min-h-0 px-2.5 py-2 font-mono text-[10px]"
              disabled={searching}
            >
              {searching ? "…" : "SEARCH"}
            </button>
          </form>

          {searchResults != null ? (
            <div>
              <div className="flex items-center justify-between px-3 py-1.5">
                <span className="eyebrow">CATALOG RESULTS</span>
                <button
                  type="button"
                  className="font-mono text-[9px] uppercase text-ink-faint hover:text-heading"
                  onClick={() => {
                    setSearchResults(null);
                    setQuery("");
                  }}
                >
                  CLEAR
                </button>
              </div>
              {searchResults.length === 0 ? (
                <p className="px-3 pb-3 text-xs text-ink-dim">No tracks match.</p>
              ) : (
                searchResults.map((t) => (
                  <TrackRow
                    key={t.id}
                    track={t}
                    queue={searchResults}
                    trailing={
                      <button
                        type="button"
                        className="btn btn-ghost !min-h-0 gap-1 px-1.5 py-2 font-mono text-[9px]"
                        onClick={() => addToCrate(t)}
                      >
                        <Plus size={13} /> ADD
                      </button>
                    }
                  />
                ))
              )}
            </div>
          ) : tab === "next" ? (
            <div>
              <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
                <label className="font-mono text-[10px] uppercase text-ink-dim" htmlFor="ref-track">
                  FROM
                </label>
                <select
                  id="ref-track"
                  className="input !min-h-0 !w-auto max-w-full flex-1 py-1.5 text-xs"
                  value={referenceId}
                  onChange={(e) => setReferenceId(e.target.value)}
                >
                  {crate.length === 0 ? <option value="">No tracks in set</option> : null}
                  {crate.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.artist} — {t.title}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  className="btn btn-ghost !min-h-0 gap-1 px-2 py-1.5 font-mono text-[10px]"
                  onClick={() => void suggest()}
                  disabled={busy || !referenceId}
                >
                  <Sparkles size={12} /> SUGGEST
                </button>
              </div>
              {reference ? (
                <p className="font-num truncate border-b border-line px-3 py-1.5 text-[10px] text-ink-dim">
                  Transitioning from: #{referenceIndex + 1}: {reference.artist} —{" "}
                  {reference.title}
                  {reference.key ? ` (${reference.key}` : " ("}
                  {reference.bpm ? `, ${fmtBpm(reference.bpm)} BPM)` : ", — BPM)"}
                </p>
              ) : null}
              {suggestions == null ? (
                <p className="px-3 py-3 text-xs text-ink-faint">
                  Pick the track you are playing now, then suggest the next one.
                </p>
              ) : suggestions.length === 0 ? (
                <p className="px-3 py-3 text-xs text-ink-dim">No compatible next track found.</p>
              ) : (
                suggestions.map((s) => (
                  <TrackRow
                    key={s.track.id}
                    track={s.track}
                    queue={suggestions.map((x) => x.track)}
                    showMatch={Math.round(s.evaluation.score)}
                    note={transitionText(s.evaluation)}
                    trailing={
                      <button
                        type="button"
                        className="btn btn-accent !min-h-0 gap-1 px-2 py-1.5 font-mono text-[9px]"
                        onClick={() => addToCrate(s.track)}
                      >
                        <Plus size={12} /> ADD TO SET
                      </button>
                    }
                  />
                ))
              )}
            </div>
          ) : (
            <div>
              <div className="grid grid-cols-1 gap-2 border-b border-line px-3 py-2 sm:grid-cols-2">
                <label className="font-mono text-[10px] uppercase text-ink-dim">
                  A
                  <select
                    className="input mt-1 !min-h-0 py-1.5 text-xs"
                    value={bridgeA}
                    onChange={(e) => setBridgeA(e.target.value)}
                    aria-label="Bridge start track"
                    disabled={crate.length === 0}
                  >
                    {crate.length === 0 ? <option value="">No tracks in set</option> : null}
                    {crate.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.artist} — {t.title}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="font-mono text-[10px] uppercase text-ink-dim">
                  B
                  <select
                    className="input mt-1 !min-h-0 py-1.5 text-xs"
                    value={bridgeB}
                    onChange={(e) => setBridgeB(e.target.value)}
                    aria-label="Bridge end track"
                    disabled={crate.length === 0}
                  >
                    {crate.length === 0 ? <option value="">No tracks in set</option> : null}
                    {crate.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.artist} — {t.title}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="flex items-center justify-between gap-2 px-3 py-2">
                <p className="text-[11px] text-ink-faint">
                  {crate.length < 2
                    ? "Add at least 2 tracks to the crate to find a harmonic bridge between them."
                    : "Find a track that connects A to B harmonically and rhythmically."}
                </p>
                <button
                  type="button"
                  className="btn btn-ghost !min-h-0 gap-1 px-2 py-1.5 font-mono text-[10px]"
                  onClick={() => void findBridge()}
                  disabled={busy || !bridgeA || !bridgeB || bridgeA === bridgeB}
                >
                  FIND BRIDGE
                </button>
              </div>
              {bridges == null ? null : bridges.length === 0 ? (
                <p className="px-3 pb-3 text-xs text-ink-dim">No bridge found.</p>
              ) : (
                bridges.map((b) => (
                  <TrackRow
                    key={b.bridge_track.id}
                    track={b.bridge_track}
                    queue={bridges.map((x) => x.bridge_track)}
                    showMatch={Math.round(b.combined_score)}
                    note={transitionText(
                      (b as unknown as { evaluation?: TransitionEvaluation }).evaluation,
                    )}
                    trailing={
                      <button
                        type="button"
                        className="btn btn-accent !min-h-0 gap-1 px-2 py-1.5 font-mono text-[9px]"
                        onClick={() => addToCrate(b.bridge_track)}
                      >
                        <Plus size={12} /> ADD TO SET
                      </button>
                    }
                  />
                ))
              )}
            </div>
          )}
        </section>
      </div>

      <section id="saved" className="panel scroll-mt-16">
        <div className="panel-head">
          <span className="eyebrow">SAVED SETS</span>
          {saved.length > 0 ? <span className="pill font-num">{saved.length}</span> : null}
        </div>
        {savedLoading && saved.length === 0 ? (
          <Loading />
        ) : saved.length === 0 ? (
          <p className="p-4 text-sm text-ink-dim">No saved sets yet.</p>
        ) : (
          <ul className="divide-y divide-line">
            {saved.map((s) => (
              <li key={s.id} className="flex flex-wrap items-center gap-2 px-3 py-2">
                <button
                  type="button"
                  className="min-w-0 flex-1 text-left"
                  onClick={() => void loadSet(s)}
                  aria-label={`Load ${s.name}`}
                >
                  <span className="block truncate text-sm text-heading">{s.name}</span>
                  <span className="font-num block text-[11px] text-ink-dim">
                    {s.track_count ?? s.track_ids?.length ?? 0} tracks ·{" "}
                    {s.updated_at?.slice(0, 10)}
                  </span>
                </button>
                <button
                  type="button"
                  className="btn !min-h-0 py-1.5"
                  onClick={() => void loadSet(s)}
                >
                  LOAD
                </button>
                <button
                  type="button"
                  className="btn !min-h-0 py-1.5"
                  onClick={() => void exportM3u8(s.id)}
                >
                  .M3U8
                </button>
                <ConfirmActionButton
                  onConfirm={() => deleteSet(s.id)}
                  label={<Trash2 size={13} />}
                  confirmLabel="DEL?"
                  className="btn btn-danger !min-h-0 py-1.5"
                  ariaLabel={`Delete ${s.name}`}
                  confirmAriaLabel={`Confirm deleting ${s.name}`}
                />
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
