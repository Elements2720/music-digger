import { useEffect, useState } from "react";
import { ArrowDown, ArrowUp, Save, Trash2, Wand2 } from "lucide-react";
import { api } from "../api/client";
import { useSettingsStore } from "../stores/settingsStore";
import { downloadPlaylist, remapM3u8 } from "../lib/m3u8";
import type { EvaluateSequenceResponse, PlannedSet } from "../types/apiTypes";
import { EmptyState, ErrorState, TrackRow } from "../components/ui";
import { useCrateStore } from "../stores/crateStore";
import { fmtClock, fmtPercent } from "../lib/format";

const FLOWS = ["any", "steady", "ramp_up", "cool_down"] as const;
type Flow = (typeof FLOWS)[number];

export function BuilderView() {
  const crate = useCrateStore((s) => s.tracks);
  const replaceAll = useCrateStore((s) => s.replaceAll);
  const clearCrate = useCrateStore((s) => s.clear);
  const [flow, setFlow] = useState<Flow>("any");
  const [evaluation, setEvaluation] = useState<EvaluateSequenceResponse | null>(null);
  const [saved, setSaved] = useState<PlannedSet[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  const refreshSaved = () => {
    api
      .listPlannedSets()
      .then(setSaved)
      .catch(() => undefined);
  };

  useEffect(refreshSaved, []);

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
    setBusy(true);
    setError(null);
    try {
      const name = `Set ${new Date().toISOString().slice(0, 10)} ${crate.length} tracks`;
      const created = await api.createPlannedSet({
        name,
        track_ids: crate.map((t) => t.id),
      });
      setStatus(`Saved "${created.name}"`);
      refreshSaved();
    } catch (err) {
      if (err instanceof Error) setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const exportM3u8 = async (id: number) => {
    try {
      const settings = useSettingsStore.getState();
      const text = remapM3u8(await api.exportPlannedSetM3u8(id), {
        pathMode: settings.m3u8PathMode,
        pathPrefix: settings.m3u8PathPrefix,
        includeMetadata: settings.m3u8IncludeMetadata,
      });
      downloadPlaylist(`set-${id}.m3u8`, text);
      setStatus("Playlist exported (.m3u8)");
    } catch (err) {
      if (err instanceof Error) setError(err.message);
    }
  };

  const loadSet = async (s: PlannedSet) => {
    try {
      const detail = await api.getPlannedSet(s.id);
      replaceAll(detail.tracks ?? []);
      setStatus(`Loaded "${detail.name}" into the crate`);
    } catch (err) {
      if (err instanceof Error) setError(err.message);
    }
  };

  const deleteSet = async (id: number) => {
    try {
      await api.deletePlannedSet(id);
      refreshSaved();
    } catch (err) {
      if (err instanceof Error) setError(err.message);
    }
  };

  const move = (index: number, dir: -1 | 1) => {
    const to = index + dir;
    if (to < 0 || to >= crate.length) return;
    const id = crate[index].id;
    useCrateStore.getState().move(id, to);
  };

  const totalSeconds = crate.reduce((acc, t) => acc + (t.duration_seconds ?? 0), 0);

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
          <Save size={14} /> SAVE SET
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
                <span className="font-num w-8 text-xs text-ink-faint">{i + 1}→{i + 2}</span>
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
                  {t.camelot_move ?? "—"} · {t.bpm_delta == null ? "—" : `${Math.round(t.bpm_delta)} BPM`}
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
                    </span>
                  }
                />
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="panel">
        <div className="panel-head">
          <span className="eyebrow">SAVED SETS</span>
        </div>
        {saved.length === 0 ? (
          <p className="p-4 text-sm text-ink-dim">No saved sets yet.</p>
        ) : (
          <ul className="divide-y divide-line">
            {saved.map((s) => (
              <li key={s.id} className="flex items-center gap-3 px-3 py-2">
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm text-heading">{s.name}</span>
                  <span className="font-num block text-[11px] text-ink-dim">
                    {s.track_count ?? s.track_ids?.length ?? 0} tracks ·{" "}
                    {s.updated_at?.slice(0, 10)}
                  </span>
                </span>
                <button type="button" className="btn !min-h-0 py-1.5" onClick={() => void loadSet(s)}>
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
