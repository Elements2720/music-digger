import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AudioWaveform, Radio } from "lucide-react";
import { api } from "../api/client";
import type { PassagePayload, SetDetailResponse, SetSummaryPayload, SetsListResponse } from "../types/apiTypes";
import { EmptyState, ErrorState, Loading, PanelHead } from "../components/ui";
import { fmtBpm, fmtClock } from "../lib/format";
import { useJobsStore } from "../stores/jobsStore";

function Timeline({ passages }: { passages: PassagePayload[] }) {
  const total = Math.max(...passages.map((p) => p.end_seconds), 1);
  return (
    <div className="panel">
      <PanelHead title="TIMELINE" />
      <div className="relative h-10 m-3" data-testid="mix-timeline">
        {passages.map((p, i) => {
          const left = (p.start_seconds / total) * 100;
          const width = ((p.end_seconds - p.start_seconds) / total) * 100;
          const bpm = p.bpm ?? 0;
          const color =
            bpm >= 130
              ? "var(--color-accent)"
              : bpm >= 120
                ? "var(--color-info)"
                : bpm > 0
                  ? "var(--color-warn)"
                  : "var(--color-line-strong)";
          return (
            <div
              key={i}
              className="absolute top-0 h-full rounded-[2px] border border-line"
              style={{ left: `${left}%`, width: `${Math.max(0.5, width)}%`, background: color, opacity: 0.75 }}
              title={`${fmtClock(p.start_seconds)}–${fmtClock(p.end_seconds)}${p.bpm ? ` · ${fmtBpm(p.bpm)} BPM` : ""}`}
            />
          );
        })}
      </div>
      <div className="flex flex-wrap gap-2 px-3 pb-3">
        {passages.slice(0, 24).map((p, i) => (
          <span key={i} className="pill font-num">
            {fmtClock(p.start_seconds)} · {p.bpm == null ? "—" : `${fmtBpm(p.bpm)}`} BPM
            {p.key ? ` · ${p.key}` : ""}
          </span>
        ))}
      </div>
    </div>
  );
}

export function MixView() {
  const [sets, setSets] = useState<SetsListResponse | null>(null);
  const [selected, setSelected] = useState<SetSummaryPayload | null>(null);
  const [detail, setDetail] = useState<SetDetailResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const job = useJobsStore((s) => s.job);
  const active = useJobsStore((s) => s.active);
  const startJob = useJobsStore((s) => s.start);

  const refresh = useCallback(() => {
    api
      .listSets(50)
      .then((res) => {
        setSets(res);
        const first = res.sets[0];
        if (first && !selected) setSelected(first);
      })
      .catch((err: unknown) => err instanceof Error && setError(err.message));
  }, [selected]);

  useEffect(refresh, [refresh]);

  useEffect(() => {
    if (!selected) return;
    let alive = true;
    setBusy(true);
    api
      .setDetail(String(selected.id), { view: "tracklist" })
      .then((res) => alive && setDetail(res))
      .catch((err: unknown) => {
        if (alive && err instanceof Error) setError(err.message);
      })
      .finally(() => alive && setBusy(false));
    return () => {
      alive = false;
    };
  }, [selected]);

  const analyze = async () => {
    const url = window.prompt("YouTube or audio URL of the DJ set to analyze");
    if (!url) return;
    try {
      await startJob("analyze-set", { source: url });
      setError(null);
    } catch (err) {
      if (err instanceof Error) setError(err.message);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h1 className="text-2xl font-bold tracking-[-0.02em] text-heading">Mix Analyzer</h1>
        <button type="button" className="btn btn-primary" onClick={() => void analyze()}>
          <AudioWaveform size={14} /> ANALYZE A SET
        </button>
      </div>

      {active && job ? (
        <div className="panel p-3" role="status">
          <p className="eyebrow text-accent">ANALYSIS RUNNING — {job.kind}</p>
          <p className="mt-1 text-xs text-ink-dim">
            {job.stage} {job.total ? `(${job.processed}/${job.total})` : ""}
          </p>
        </div>
      ) : null}

      {error ? <ErrorState message={error} /> : null}

      {!sets ? (
        <Loading label="LOADING SETS…" />
      ) : sets.sets.length === 0 ? (
        <EmptyState
          title="NO DJ SETS ANALYZED"
          hint="Analyze a recorded set to extract its BPM/key timeline and identify the tracks inside it."
          action={
            <button type="button" className="btn btn-primary" onClick={() => void analyze()}>
              <Radio size={14} /> ANALYZE YOUR FIRST SET
            </button>
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[280px_1fr]">
          <div className="panel self-start">
            <PanelHead title="SETS" />
            <ul className="divide-y divide-line">
              {sets.sets.map((s) => (
                <li key={s.id}>
                  <button
                    type="button"
                    onClick={() => setSelected(s)}
                    className={`w-full px-3 py-2 text-left hover:bg-panel-2 ${
                      selected?.id === s.id ? "bg-panel-2" : ""
                    }`}
                  >
                    <span className="block truncate text-sm text-heading">{s.title}</span>
                    <span className="font-num block text-[11px] text-ink-dim">
                      {s.passage_count} passages
                      {s.bpm_min != null && s.bpm_max != null
                        ? ` · ${fmtBpm(s.bpm_min)}–${fmtBpm(s.bpm_max)} BPM`
                        : ""}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>

          <div className="flex flex-col gap-4">
            {busy && !detail ? <Loading label="LOADING SET…" /> : null}
            {detail ? (
              detail.view === "tracklist" && detail.passages ? (
                <>
                  <Timeline passages={detail.passages} />
                  <section className="panel">
                    <PanelHead title="IDENTIFIED PASSAGES" />
                    <div className="divide-y divide-line">
                      {detail.passages.map((p, i) => {
                        const m = p.matches[0];
                        return (
                          <div key={i} className="flex items-center gap-3 px-3 py-2">
                            <span className="font-num w-16 text-[11px] text-ink-faint">
                              {fmtClock(p.start_seconds)}
                            </span>
                            {m ? (
                              <Link
                                to={`/dig?mode=match`}
                                className="min-w-0 flex-1 truncate text-sm text-heading hover:text-accent"
                              >
                                {m.track.artist} — {m.track.title}
                              </Link>
                            ) : (
                              <span className="min-w-0 flex-1 truncate text-sm text-ink-faint">
                                {p.exact_id_display_name ?? "Unidentified passage"}
                              </span>
                            )}
                            {m ? (
                              <span className="pill font-num">
                                {Math.round(m.similarity * 100)}%
                              </span>
                            ) : null}
                            {p.bpm != null ? (
                              <span className="pill font-num hidden sm:inline-flex">
                                {fmtBpm(p.bpm)} BPM
                              </span>
                            ) : null}
                            {p.key ? <span className="pill pill-key font-num hidden md:inline-flex">{p.key}</span> : null}
                          </div>
                        );
                      })}
                    </div>
                  </section>
                </>
              ) : null
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}
