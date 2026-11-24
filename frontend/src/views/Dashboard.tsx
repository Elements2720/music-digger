import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { DashboardResponse } from "../types/apiTypes";
import { ErrorState, Loading, PanelHead, TrackRow } from "../components/ui";
import { fmtCount } from "../lib/format";
import { useJobsStore } from "../stores/jobsStore";

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div className="panel p-4">
      <p className="eyebrow">{label}</p>
      <p className="font-num mt-2 text-2xl text-heading" data-kpi={label}>
        {value}
      </p>
    </div>
  );
}

function CamelotWheel({
  keys,
}: {
  keys: { camelot_key: string | null; track_count: number }[];
}) {
  const real = keys.filter((k) => k.camelot_key);
  if (real.length === 0) return null;
  const max = Math.max(...real.map((k) => k.track_count));
  const segments = Array.from({ length: 12 }, (_, i) => i + 1);
  return (
    <div className="panel">
      <PanelHead title="CAMELOT WHEEL — TRACKS PER KEY" />
      <div className="grid grid-cols-6 gap-1 p-3 sm:grid-cols-12">
        {segments.map((n) => {
          const major = real.find((k) => k.camelot_key === `${n}B`);
          const minor = real.find((k) => k.camelot_key === `${n}A`);
          const count = (major?.track_count ?? 0) + (minor?.track_count ?? 0);
          const intensity = count === 0 ? 0 : 0.25 + (count / max) * 0.75;
          return (
            <Link
              key={n}
              to={`/dig?mode=vibe&camelot=${n}A`}
              className="flex flex-col items-center justify-center rounded-[3px] border border-line p-1.5 transition-colors hover:border-line-strong"
              style={{
                background: `color-mix(in srgb, var(--color-accent) ${intensity * 30}%, var(--color-panel-2))`,
              }}
              aria-label={`Dig key ${n}A, ${count} tracks`}
            >
              <span className="font-num text-[11px] text-heading">{n}</span>
              <span className="font-num text-[9px] text-ink-faint">{count}</span>
            </Link>
          );
        })}
      </div>
    </div>
  );
}

function BpmHistogram({
  buckets,
}: {
  buckets: { label: string; track_count: number }[];
}) {
  if (buckets.length === 0) return null;
  const max = Math.max(...buckets.map((b) => b.track_count));
  return (
    <div className="panel">
      <PanelHead title="BPM HISTOGRAM" />
      <div className="flex h-36 items-end gap-1 p-3">
        {buckets.map((b) => (
          <div key={b.label} className="flex min-w-0 flex-1 flex-col items-center gap-1">
            <span className="font-num text-[9px] text-ink-faint">{b.track_count}</span>
            <div
              className="w-full rounded-t-[2px] bg-accent/70"
              style={{ height: `${Math.max(4, (b.track_count / max) * 100)}%` }}
              title={`${b.label}: ${b.track_count}`}
            />
            <span className="font-num text-[9px] text-ink-faint">{b.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function DashboardView() {
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const job = useJobsStore((s) => s.job);
  const active = useJobsStore((s) => s.active);

  useEffect(() => {
    let alive = true;
    api
      .dashboard()
      .then((res) => alive && setData(res))
      .catch((err: unknown) =>
        alive && err instanceof Error ? setError(err.message) : undefined,
      );
    return () => {
      alive = false;
    };
  }, []);

  if (error) return <ErrorState message={error} />;
  if (!data) return <Loading label="LOADING DASHBOARD…" />;

  const { stats, analytics, recent_tracks: recent } = data;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-baseline justify-between gap-4">
        <h1 className="text-2xl font-bold tracking-[-0.02em] text-heading">
          Every key, knob and cue in one console.
        </h1>
      </div>

      {active && job ? (
        <div className="panel p-3" role="status">
          <p className="eyebrow text-accent">JOB RUNNING — {job.kind}</p>
          <p className="mt-1 text-xs text-ink-dim">
            {job.stage} {job.total ? `(${job.processed}/${job.total})` : ""}
          </p>
        </div>
      ) : null}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Kpi label="TRACKS" value={fmtCount(analytics?.total_tracks ?? stats.tracks.total)} />
        <Kpi label="EMBEDDED" value={fmtCount(analytics?.total_embedded ?? stats.tracks.embedded)} />
        <Kpi label="ARTISTS" value={fmtCount(analytics?.total_artists ?? 0)} />
        <Kpi label="LOCAL FILES" value={fmtCount(analytics?.total_local ?? 0)} />
        <Kpi label="SEEDS" value={fmtCount(stats.seeds.total)} />
        <Kpi label="DJ SETS" value={fmtCount(stats.sets.total)} />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <CamelotWheel keys={analytics?.top_keys ?? []} />
        <BpmHistogram buckets={analytics?.bpm_buckets ?? []} />
      </div>

      <section className="panel">
        <PanelHead
          title="RECENTLY INDEXED"
          right={
            <Link to="/dig" className="btn btn-ghost !min-h-0 py-1.5">
              OPEN DIG
            </Link>
          }
        />
        {recent.length === 0 ? (
          <p className="p-6 text-sm text-ink-dim">
            Nothing indexed yet — run the Pipeline jobs to build your catalog.
          </p>
        ) : (
          recent.slice(0, 12).map((t) => <TrackRow key={t.id} track={t} queue={recent} />)
        )}
      </section>
    </div>
  );
}
