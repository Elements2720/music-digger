import { useEffect, useMemo, useState } from "react";
import {
  ArrowDown,
  ArrowRightLeft,
  ArrowUp,
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
} from "../types/apiTypes";
import { EmptyState, ErrorState, Loading, TrackRow } from "../components/ui";
import { useCrateStore } from "../stores/crateStore";
import { useJobsStore } from "../stores/jobsStore";
import { fmtClock, fmtPercent } from "../lib/format";

const FLOWS = ["any", "steady", "ramp_up", "cool_down"] as const;
type Flow = (typeof FLOWS)[number];

function activeSetFlow() {
  const settings = useSettingsStore.getState();
  return {
    pathMode: settings.m3u8PathMode,
    pathPrefix: settings.m3u8PathPrefix,
    includeMetadata: settings.m3u8IncludeMetadata,
  };
}

export function BuilderView() {
  const crate = useCrateStore((s) => s.tracks);
  const replaceAll = useCrateStore((s) => s.replaceAll);
  const clearCrate = useCrateStore((s) => s.clear);
  const addToCrate = useCrateStore((s) => s.add);
  const startJob = useJobsStore((s) => s.start);
  const [flow, setFlow] = useState<Flow>("any");
  const [evaluation, setEvaluation] = useState<EvaluateSequenceResponse | null>(null);
  const [saved, setSaved] = useState<PlannedSet[]>([]);
  const [name, setName] = useState("");
  const [loadedSetId, setLoadedSetId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  const [referenceId, setReferenceId] = useState("");
  const [localOnly, setLocalOnly] = useState(false);
  const [suggestions, setSuggestions] = useState<NextTrackSuggestion[] | null>(null);
  const [bridgeA, setBridgeA] = useState("");
  const [bridgeB, setBridgeB] = useState("");
  const [bridges, setBridges] = useState<BridgeSuggestion[] | null>(null);
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<Track[] | null>(null);

  const refreshSaved = () => {
    api
      .listPlannedSets()
      .then(setSaved)
      .catch(() => undefined);
  };

  useEffect(refreshSaved, []);

  useEffect(() => {
    if (!referenceId && crate.length > 0) setReferenceId(crate[crate.length - 1].id);
    if (!bridgeA && crate.length > 0) setBridgeA(crate[0].id);
    if (!bridgeB && crate.length > 1) setBridgeB(crate[crate.length - 1].id);
  }, [crate, referenceId, bridgeA, bridgeB]);

  const totalSeconds = crate.reduce((acc, t) => acc + (t.duration_seconds ?? 0), 0);
  const missingLocal = useMemo(() => crate.filter((t) => !t.has_local_file), [crate]);

  const autoSequence = async () => {
    if (crate.length < 2) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.autoSequence({
        track_ids: crate.map((t) => t.id),
        flow,
        lock_first: true,
      });
      const byId = new Map(crate.map((t) => [t.id, t]));
      const ordered = res.ordered_track_ids
        .map((id) => byId.get(id))
        .filter((t): t is NonNullable<typeof t> => Boolean(t));
      replaceAll(ordered);
      setStatus(`Sequenced ${ordered.length} tracks (avg score ${fmtPercent(res.average_score * 100)})`);
    } catch (err) {
      if (err instanceof Error) setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const evaluate = async () => {
    if (crate.length < 2) return;
    setBusy(true);
    setError(null);
    try {
      setEvaluation(await api.evaluate({ track_ids: crate.map((t) => t.id), flow }));
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

  const search = async () => {
    if (!query.trim()) return;
    try {
      const res = await api.searchTracks(query.trim(), 10);
      setSearchResults(res.tracks);
    } catch (err) {
      if (err instanceof Error) setError(err.message);
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

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h1 className="text-2xl font-bold tracking-[-0.02em] text-heading">Set Builder</h1>
        <span className="font-num text-xs text-ink-dim">
          {crate.length} TRACKS · {fmtClock(totalSeconds)}
        </span>
      </div>

      {error ? <ErrorState message={error} /> : null}
      {status ? (
        <p className="font-mono text-xs text-accent" role="status">
          {status}
        </p>
      ) : null}

      <div className="panel flex flex-wrap items-center gap-2 p-3">
        <input
          className="input min-w-[180px] flex-1"
          placeholder="Set name…"
          value={name}
          onChange={(e) => setName(e.target.value)}
          aria-label="Set name"
        />
        <label className="eyebrow" htmlFor="flow">
          FLOW
        </label>
        <select
          id="flow"
          className="input !w-auto"
          value={flow}
          onChange={(e) => setFlow(e.target.value as Flow)}
        >
          {FLOWS.map((f) => (
            <option key={f} value={f}>
              {f.toUpperCase()}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="btn"
          onClick={() => void autoSequence()}
          disabled={busy || crate.length < 2}
        >
          <Wand2 size={14} /> AUTO-SEQUENCE
        </button>
        <button
          type="button"
          className="btn"
          onClick={() => void evaluate()}
          disabled={busy || crate.length < 2}
        >
          EVALUATE
        </button>
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => void saveSet()}
          disabled={busy || crate.length === 0}
        >
          <Save size={14} /> {loadedSetId != null ? "UPDATE SET" : "SAVE SET"}
        </button>
        <button
          type="button"
          className="btn"
          onClick={exportCrate}
          disabled={crate.length === 0}
        >
          <FileDown size={14} /> .M3U8
        </button>
        <button
          type="button"
          className="btn"
          onClick={() => void downloadMissing()}
          disabled={missingLocal.length === 0}
          title="Download previews for tracks that have no local file"
        >
          <Download size={14} /> DL MISSING{missingLocal.length ? ` (${missingLocal.length})` : ""}
        </button>
        <button
          type="button"
          className="btn btn-danger"
          onClick={clearCrate}
          disabled={crate.length === 0}
        >
          <Trash2 size={14} /> CLEAR
        </button>
      </div>

      {evaluation ? (
        <section className="panel">
          <div className="panel-head">
            <span className="eyebrow">TRANSITIONS — 0 TO 100 SCORE</span>
          </div>
          <div className="divide-y divide-line">
            {evaluation.transitions.map((t, i) => (
              <div key={i} className="flex items-center gap-3 px-3 py-2">
                <span className="font-num w-8 text-xs text-ink-faint">
                  {i + 1}→{i + 2}
                </span>
                <div className="h-2 flex-1 rounded bg-fill">
                  <div
                    className="h-full rounded"
                    style={{
                      width: `${Math.max(2, Math.min(100, t.score))}%`,
                      background:
                        t.score >= 66
                          ? "var(--color-accent)"
                          : t.score >= 33
                            ? "var(--color-warn)"
                            : "var(--color-danger)",
                    }}
                  />
                </div>
                <span className="font-num w-12 text-right text-xs text-heading">
                  {Math.round(t.score)}%
                </span>
                <span className="font-num hidden w-24 text-right text-[11px] text-ink-dim sm:block">
                  {t.camelot_move ?? "—"} ·{" "}
                  {t.bpm_delta == null ? "—" : `${Math.round(t.bpm_delta)} BPM`}
                </span>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <section>
        {crate.length === 0 ? (
          <EmptyState
            title="CRATE EMPTY"
            hint="Add tracks from Dashboard, Dig or Library with the + Set action, then sequence and save them here."
          />
        ) : (
          <div className="panel">
            {crate.map((t, i) => (
              <div key={t.id} className="flex flex-col border-b border-line last:border-b-0">
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
                        aria-label={`Move ${t.title} up`}
                      >
                        <ArrowUp size={13} />
                      </button>
                      <button
                        type="button"
                        className="btn btn-ghost !min-h-0 p-1.5"
                        onClick={() => move(i, 1)}
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
              </div>
            ))}
          </div>
        )}
      </section>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <section className="panel self-start">
          <div className="panel-head">
            <span className="eyebrow">NEXT TRACK</span>
            <button type="button" className="btn !min-h-0 py-1.5" onClick={() => void suggest()}>
              <Sparkles size={13} /> SUGGEST
            </button>
          </div>
          <div className="flex flex-wrap items-center gap-2 px-3 py-2">
            <label className="font-mono text-[10px] uppercase text-ink-dim" htmlFor="ref-track">
              FROM
            </label>
            <select
              id="ref-track"
              className="input !w-auto max-w-full flex-1"
              value={referenceId}
              onChange={(e) => setReferenceId(e.target.value)}
            >
              {crate.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.artist} — {t.title}
                </option>
              ))}
            </select>
            <label className="flex items-center gap-2 font-mono text-[10px] uppercase text-ink-dim">
              <input
                type="checkbox"
                checked={localOnly}
                onChange={(e) => setLocalOnly(e.target.checked)}
                className="h-4 w-4 accent-accent"
              />
              LOCAL ONLY
            </label>
          </div>
          {suggestions == null ? (
            <p className="px-3 pb-3 text-xs text-ink-faint">
              Pick the track you are playing now, then suggest the next one.
            </p>
          ) : suggestions.length === 0 ? (
            <p className="px-3 pb-3 text-xs text-ink-dim">No compatible next track found.</p>
          ) : (
            <div className="border-t border-line">
              {suggestions.map((s) => (
                <TrackRow
                  key={s.track.id}
                  track={s.track}
                  showMatch={Math.round(s.evaluation.score)}
                  trailing={
                    <button
                      type="button"
                      className="btn btn-ghost !min-h-0 px-1.5 py-2 font-mono text-[9px]"
                      onClick={() => addToCrate(s.track)}
                    >
                      <Plus size={13} />
                    </button>
                  }
                />
              ))}
            </div>
          )}
        </section>

        <section className="panel self-start">
          <div className="panel-head">
            <span className="eyebrow">FIND BRIDGE</span>
            <button type="button" className="btn !min-h-0 py-1.5" onClick={() => void findBridge()}>
              <ArrowRightLeft size={13} /> BRIDGE
            </button>
          </div>
          <div className="grid grid-cols-1 gap-2 px-3 py-2 sm:grid-cols-2">
            <label className="font-mono text-[10px] uppercase text-ink-dim">
              A
              <select
                className="input mt-1"
                value={bridgeA}
                onChange={(e) => setBridgeA(e.target.value)}
                aria-label="Bridge start track"
              >
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
                className="input mt-1"
                value={bridgeB}
                onChange={(e) => setBridgeB(e.target.value)}
                aria-label="Bridge end track"
              >
                {crate.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.artist} — {t.title}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {bridges == null ? (
            <p className="px-3 pb-3 text-xs text-ink-faint">
              Find a track that connects A to B harmonically and rhythmically.
            </p>
          ) : bridges.length === 0 ? (
            <p className="px-3 pb-3 text-xs text-ink-dim">No bridge found.</p>
          ) : (
            <div className="border-t border-line">
              {bridges.map((b) => (
                <TrackRow
                  key={b.bridge_track.id}
                  track={b.bridge_track}
                  showMatch={Math.round(b.combined_score)}
                  trailing={
                    <button
                      type="button"
                      className="btn btn-ghost !min-h-0 px-1.5 py-2 font-mono text-[9px]"
                      onClick={() => addToCrate(b.bridge_track)}
                    >
                      <Plus size={13} />
                    </button>
                  }
                />
              ))}
            </div>
          )}
        </section>
      </div>

      <section className="panel">
        <div className="panel-head">
          <span className="eyebrow">ADD FROM CATALOG</span>
        </div>
        <form
          className="flex gap-2 p-3"
          onSubmit={(e) => {
            e.preventDefault();
            void search();
          }}
        >
          <div className="relative flex-1">
            <Search
              size={14}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint"
              aria-hidden
            />
            <input
              className="input pl-10"
              placeholder="Search the catalog…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label="Search the catalog"
            />
          </div>
          <button type="submit" className="btn">
            SEARCH
          </button>
        </form>
        {searchResults == null ? null : searchResults.length === 0 ? (
          <p className="px-3 pb-3 text-xs text-ink-dim">No tracks match.</p>
        ) : (
          <div className="border-t border-line">
            {searchResults.map((t) => (
              <TrackRow
                key={t.id}
                track={t}
                queue={searchResults}
                trailing={
                  <button
                    type="button"
                    className="btn btn-ghost !min-h-0 px-1.5 py-2 font-mono text-[9px]"
                    onClick={() => addToCrate(t)}
                  >
                    <Plus size={13} />
                  </button>
                }
              />
            ))}
          </div>
        )}
      </section>

      <section className="panel">
        <div className="panel-head">
          <span className="eyebrow">SAVED SETS</span>
          {saved.length > 0 ? <span className="pill font-num">{saved.length}</span> : null}
        </div>
        {saved.length === 0 ? (
          <p className="p-4 text-sm text-ink-dim">No saved sets yet.</p>
        ) : busy ? (
          <Loading />
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
                <button
                  type="button"
                  className="btn btn-danger !min-h-0 py-1.5"
                  onClick={() => void deleteSet(s.id)}
                  aria-label={`Delete ${s.name}`}
                >
                  <Trash2 size={13} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
