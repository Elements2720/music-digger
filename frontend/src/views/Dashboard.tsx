import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ChevronLeft, ChevronRight, RefreshCw } from "lucide-react";
import { api } from "../api/client";
import type { DashboardResponse, Track } from "../types/apiTypes";
import {
  AlbumCard,
  EmptyState,
  ErrorState,
  Loading,
  PanelHead,
  TrackRow,
} from "../components/ui";
import { fmtCount } from "../lib/format";
import { useJobsStore } from "../stores/jobsStore";

// --------------------------------------------------------------- camelot

type KeyCount = { camelot_key: string | null; track_count: number };

const CENTER = 160;
const OUTER = { r0: 150, r1: 112, label: 131 };
const INNER = { r0: 108, r1: 70, label: 89 };

function polar(radius: number, deg: number): [number, number] {
  const rad = ((deg - 90) * Math.PI) / 180;
  return [CENTER + radius * Math.cos(rad), CENTER + radius * Math.sin(rad)];
}

function wedge(r0: number, r1: number, a0: number, a1: number): string {
  const [x0, y0] = polar(r0, a0);
  const [x1, y1] = polar(r0, a1);
  const [x2, y2] = polar(r1, a1);
  const [x3, y3] = polar(r1, a0);
  const large = a1 - a0 > 180 ? 1 : 0;
  return [
    `M ${x0.toFixed(2)} ${y0.toFixed(2)}`,
    `A ${r0} ${r0} 0 ${large} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`,
    `L ${x2.toFixed(2)} ${y2.toFixed(2)}`,
    `A ${r1} ${r1} 0 ${large} 0 ${x3.toFixed(2)} ${y3.toFixed(2)}`,
    "Z",
  ].join(" ");
}

function CamelotWheel({ keys }: { keys: KeyCount[] }) {
  const navigate = useNavigate();
  const [focusIdx, setFocusIdx] = useState(0);
  const wheelRef = useRef<SVGSVGElement | null>(null);
  const real = keys.filter((k) => k.camelot_key);
  const max = real.length ? Math.max(...real.map((k) => k.track_count)) : 0;
  const total = real.reduce((sum, k) => sum + k.track_count, 0);
  const countFor = (key: string) =>
    real.find((k) => k.camelot_key === key)?.track_count ?? 0;

  const moveFocus = (nextIdx: number) => {
    const wrapped = ((nextIdx % 24) + 24) % 24;
    setFocusIdx(wrapped);
    const items = wheelRef.current?.querySelectorAll<SVGGElement>(".wheel-seg");
    items?.[wrapped]?.focus();
  };

  return (
    <section className="panel overflow-hidden" aria-label="Camelot wheel">
      <PanelHead
        title="CAMELOT WHEEL"
        right={
          <span className="font-mono text-[9px] uppercase tracking-[0.14em] text-ink-faint">
            {fmtCount(total)} mapped
          </span>
        }
      />
      {real.length === 0 ? (
        <EmptyState
          title="No keys mapped yet"
          hint="Index tracks with BPM/key analysis to plot them on the wheel."
        />
      ) : (
        <div className="grid gap-2 p-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
          <div className="mx-auto w-full max-w-[320px]">
            <svg
              ref={wheelRef}
              viewBox="0 0 320 320"
              role="group"
              aria-label="Camelot wheel, 24 keys"
              className="h-auto w-full"
            >
              {Array.from({ length: 12 }, (_, i) => i + 1).map((n) => {
                const centerAngle = n === 12 ? 0 : n * 30;
                const a0 = centerAngle - 14;
                const a1 = centerAngle + 14;
                return [
                  { key: `${n}B`, ring: OUTER, name: "B major" },
                  { key: `${n}A`, ring: INNER, name: "A minor" },
                ].map(({ key, ring, name }, ringIdx) => {
                  const idx = (n - 1) * 2 + ringIdx;
                  const count = countFor(key);
                  const mix =
                    count === 0
                      ? 0
                      : 14 + Math.round((count / max) * 48);
                  const [lx, ly] = polar(ring.label, centerAngle);
                  return (
                    <g
                      key={key}
                      className="wheel-seg"
                      role="link"
                      tabIndex={idx === focusIdx ? 0 : -1}
                      aria-label={`Dig ${key} ${name}, ${count} tracks`}
                      onFocus={() => setFocusIdx(idx)}
                      onClick={() =>
                        navigate(`/dig?mode=vibe&camelot=${key}`)
                      }
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          navigate(`/dig?mode=vibe&camelot=${key}`);
                        } else if (e.key === "ArrowRight" || e.key === "ArrowDown") {
                          e.preventDefault();
                          moveFocus(idx + 1);
                        } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
                          e.preventDefault();
                          moveFocus(idx - 1);
                        }
                      }}
                    >
                      <title>{`${key} ${name} — ${count} tracks`}</title>
                      <path
                        d={wedge(ring.r0, ring.r1, a0, a1)}
                        fill={
                          count === 0
                            ? "var(--color-panel-2)"
                            : `color-mix(in srgb, var(--color-accent) ${mix}%, var(--color-panel-2))`
                        }
                        stroke="var(--color-line)"
                        strokeWidth={1}
                      />
                      <text
                        x={lx}
                        y={ly}
                        textAnchor="middle"
                        dominantBaseline="central"
                        fontFamily="var(--font-mono)"
                        fontSize={10}
                        fontWeight={500}
                        fill={
                          count === 0
                            ? "var(--color-ink-faint)"
                            : "var(--color-heading)"
                        }
                        pointerEvents="none"
                      >
                        {key}
                      </text>
                    </g>
                  );
                });
              })}
              <text
                x={CENTER}
                y={CENTER - 14}
                textAnchor="middle"
                fontFamily="var(--font-mono)"
                fontSize={8}
                letterSpacing={2}
                fill="var(--color-ink-faint)"
              >
                CAMELOT
              </text>
              <text
                x={CENTER}
                y={CENTER + 8}
                textAnchor="middle"
                fontFamily="var(--font-mono)"
                fontSize={20}
                fill="var(--color-heading)"
              >
                {fmtCount(total)}
              </text>
              <text
                x={CENTER}
                y={CENTER + 24}
                textAnchor="middle"
                fontFamily="var(--font-mono)"
                fontSize={7}
                letterSpacing={1.4}
                fill="var(--color-ink-faint)"
              >
                TRACKS MAPPED
              </text>
            </svg>
          </div>
          <div className="flex flex-col gap-2 sm:w-36">
            <p className="eyebrow">Rings</p>
            <div className="flex items-center gap-2 font-mono text-[10px] text-ink-dim">
              <span
                aria-hidden
                className="h-2.5 w-2.5"
                style={{
                  background:
                    "color-mix(in srgb, var(--color-accent) 40%, var(--color-panel-2))",
                }}
              />
              Outer · 12B
            </div>
            <div className="flex items-center gap-2 font-mono text-[10px] text-ink-dim">
              <span
                aria-hidden
                className="h-2.5 w-2.5"
                style={{
                  background:
                    "color-mix(in srgb, var(--color-accent) 22%, var(--color-panel-2))",
                }}
              />
              Inner · 12A
            </div>
            <p className="mt-1 border-t border-line pt-2 font-mono text-[9px] uppercase leading-relaxed tracking-[0.1em] text-ink-faint">
              Shade = track density. Click a key to open Dig pre-filtered.
            </p>
          </div>
        </div>
      )}
    </section>
  );
}

// ----------------------------------------------------------------- bpm

function bpmLabelToRange(label: string): { min?: number; max?: number } | null {
  const under = /^<\s*(\d+)$/.exec(label);
  if (under) return { max: Number(under[1]) - 1 };
  const over = /^(\d+)\+$/.exec(label);
  if (over) return { min: Number(over[1]) };
  const span = /^(\d+)\s*-\s*(\d+)$/.exec(label);
  if (span) return { min: Number(span[1]), max: Number(span[2]) };
  return null;
}

function BpmHistogram({
  buckets,
}: {
  buckets: { label: string; track_count: number }[];
}) {
  const max = buckets.length
    ? Math.max(...buckets.map((b) => b.track_count))
    : 0;
  return (
    <section className="panel overflow-hidden" aria-label="BPM histogram">
      <PanelHead
        title="BPM HISTOGRAM"
        right={
          <span className="font-mono text-[9px] uppercase tracking-[0.14em] text-ink-faint">
            {buckets.length ? `${buckets.length} buckets` : "no data"}
          </span>
        }
      />
      {buckets.length === 0 ? (
        <EmptyState
          title="No tempo data yet"
          hint="Analyze tracks in the Pipeline to fill the histogram."
        />
      ) : (
        <div className="px-3 pb-3 pt-4">
          <div className="flex h-[132px] items-end gap-1.5">
            {buckets.map((b) => {
              const range = bpmLabelToRange(b.label);
              const qs = new URLSearchParams({ mode: "vibe" });
              if (range?.min != null) qs.set("bpm_min", String(range.min));
              if (range?.max != null) qs.set("bpm_max", String(range.max));
              const to = range ? `/dig?${qs.toString()}` : null;
              const height = Math.max(
                6,
                Math.round((b.track_count / max) * 92),
              );
              const bar = (
                <>
                  <span className="bar-count font-num text-[9px] leading-none text-ink-faint">
                    {b.track_count}
                  </span>
                  <span
                    className="bar-fill w-full shrink-0 rounded-t-[3px]"
                    style={{
                      height,
                      background:
                        "color-mix(in srgb, var(--color-accent) 62%, transparent)",
                    }}
                  />
                  <span className="font-num w-full truncate text-center text-[8px] leading-none text-ink-faint sm:text-[9px]">
                    {b.label}
                  </span>
                </>
              );
              const classes =
                "bar-hit flex h-full min-w-0 flex-1 flex-col items-center justify-end gap-1";
              return to ? (
                <Link
                  key={b.label}
                  to={to}
                  className={classes}
                  title={`Filter catalog to ${b.label} BPM`}
                  aria-label={`Dig ${b.label} BPM, ${b.track_count} tracks`}
                >
                  {bar}
                </Link>
              ) : (
                <div
                  key={b.label}
                  className={classes}
                  title={`${b.label}: ${b.track_count}`}
                >
                  {bar}
                </div>
              );
            })}
          </div>
          <div className="mt-2 flex items-center justify-between border-t border-line pt-2 font-mono text-[8px] uppercase tracking-[0.12em] text-ink-faint">
            <span>0 BPM</span>
            <span>Click a bar to dig that window</span>
            <span>200 BPM</span>
          </div>
        </div>
      )}
    </section>
  );
}

// --------------------------------------------------------------- shelf

function ShelfArrows({
  onScroll,
  className = "",
}: {
  onScroll: (dir: -1 | 1) => void;
  className?: string;
}) {
  return (
    <div className={`flex items-center gap-1.5 ${className}`}>
      <button
        type="button"
        onClick={() => onScroll(-1)}
        className="flex h-8 w-8 items-center justify-center rounded-full border border-line bg-white/[0.04] text-ink-dim transition-colors hover:border-white/25 hover:text-heading"
        aria-label="Scroll shelf left"
      >
        <ChevronLeft size={15} />
      </button>
      <button
        type="button"
        onClick={() => onScroll(1)}
        className="flex h-8 w-8 items-center justify-center rounded-full border border-line bg-white/[0.04] text-ink-dim transition-colors hover:border-white/25 hover:text-heading"
        aria-label="Scroll shelf right"
      >
        <ChevronRight size={15} />
      </button>
    </div>
  );
}

function TopPicks() {
  const [tracks, setTracks] = useState<Track[] | null>(null);
  const [failed, setFailed] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .tasteRanking({ mode: "both", limit: 16 })
      .then((res) => alive && setTracks(res.matches))
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
  }, []);

  const scroll = (dir: -1 | 1) => {
    ref.current?.scrollBy({ left: dir * 360, behavior: "smooth" });
  };

  return (
    <section className="panel overflow-hidden">
      <div className="flex items-center justify-between gap-3 px-5 py-3">
        <p className="eyebrow">Top picks for you</p>
        <div className="flex items-center gap-2">
          <ShelfArrows onScroll={scroll} className="hidden sm:flex" />
          <Link to="/dig" className="btn btn-ghost !min-h-0 py-1.5">
            Open Dig
          </Link>
        </div>
      </div>
      {failed ? (
        <p className="border-t border-line px-5 py-4 text-[12px] text-ink-faint">
          Taste ranking is unavailable right now — start Digging to seed it.
        </p>
      ) : tracks === null ? (
        <div className="flex gap-3 border-t border-line px-5 py-4">
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <div
              key={i}
              className="h-[176px] w-[144px] shrink-0 animate-pulse rounded-[10px] bg-white/[0.04] sm:w-[164px]"
            />
          ))}
        </div>
      ) : tracks.length === 0 ? (
        <p className="border-t border-line px-5 py-4 text-[12px] text-ink-faint">
          No picks yet — like a few tracks or run the catalog index to build your taste
          profile.
        </p>
      ) : (
        <div
          ref={ref}
          className="shelf no-scrollbar border-t border-line px-5 py-4 scroll-px-5"
        >
          {tracks.map((t) => (
            <AlbumCard key={t.id} track={t} queue={tracks} />
          ))}
        </div>
      )}
    </section>
  );
}

// ------------------------------------------------------------ top genres

function TopGenres({ genres }: { genres: { genre: string; track_count: number }[] }) {
  const rows = genres.slice(0, 8);
  const max = rows.length ? Math.max(...rows.map((g) => g.track_count)) : 0;
  return (
    <section className="panel overflow-hidden" aria-label="Top genres">
      <PanelHead
        title="TOP GENRES"
        right={
          <span className="font-mono text-[9px] uppercase tracking-[0.14em] text-ink-faint">
            {genres.length ? `${genres.length} genres` : "no data"}
          </span>
        }
      />
      {rows.length === 0 ? (
        <EmptyState
          title="No genre data yet"
          hint="Index tracks to chart the genres in your crate."
        />
      ) : (
        <div className="flex flex-col gap-2 px-3 py-3.5">
          {rows.map((g) => {
            const pct = max ? Math.max(3, Math.round((g.track_count / max) * 100)) : 0;
            return (
              <div key={g.genre} className="flex items-center gap-2.5">
                <span className="w-[86px] shrink-0 truncate text-[11px] leading-tight text-ink-dim sm:w-[104px]">
                  {g.genre}
                </span>
                <span className="h-[7px] min-w-0 flex-1 overflow-hidden rounded-[2px] bg-white/[0.05]">
                  <span
                    className="block h-full rounded-[2px]"
                    style={{
                      width: `${pct}%`,
                      background:
                        "linear-gradient(90deg, var(--color-accent), color-mix(in srgb, var(--color-accent) 45%, transparent))",
                    }}
                  />
                </span>
                <span className="font-num w-[44px] shrink-0 text-right text-[10px] leading-none text-ink-faint">
                  {fmtCount(g.track_count)}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

// ----------------------------------------------------------- dashboard

type Kpi = {
  label: string;
  value: (d: DashboardResponse) => number;
  sub?: (d: DashboardResponse) => string;
};

function pct(part: number, whole: number): string {
  return whole > 0 ? `${Math.round((part / whole) * 100)}%` : "0%";
}

const KPIS: Kpi[] = [
  {
    label: "TOTAL TRACKS",
    value: (d) => d.analytics?.total_tracks ?? d.stats.tracks.total,
    sub: (d) =>
      `${pct(d.analytics?.total_embedded ?? 0, d.analytics?.total_tracks || 1)} embedded`,
  },
  {
    label: "EMBEDDED",
    value: (d) => d.analytics?.total_embedded ?? d.stats.tracks.embedded,
    sub: (d) =>
      `${pct(d.analytics?.total_embedded ?? 0, d.analytics?.total_tracks || 1)} ready`,
  },
  {
    label: "TOTAL ARTISTS",
    value: (d) => d.analytics?.total_artists ?? 0,
  },
  {
    label: "LOCAL FILES",
    value: (d) => d.analytics?.total_local ?? 0,
  },
  {
    label: "ITUNES TRACKS",
    value: (d) => d.analytics?.total_itunes ?? 0,
  },
  {
    label: "DJ SETS",
    value: (d) => d.stats.sets.total,
    sub: () => "analyzed",
  },
  {
    label: "SEED ARTISTS",
    value: (d) => d.stats.seeds.total,
    sub: (d) => `${fmtCount(d.stats.seeds.pending)} pending`,
  },
  {
    label: "TASTE PROFILE",
    value: (d) => d.analytics?.local_taste_count ?? 0,
    sub: (d) => `${fmtCount(d.analytics?.local_taste_count ?? 0)} local tracks active`,
  },
];

export function DashboardView() {
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const job = useJobsStore((s) => s.job);
  const active = useJobsStore((s) => s.active);

  useEffect(() => {
    let alive = true;
    setRefreshing(true);
    api
      .dashboard()
      .then((res) => {
        if (!alive) return;
        setData(res);
        setError(null);
      })
      .catch((err: unknown) =>
        alive && err instanceof Error ? setError(err.message) : undefined,
      )
      .finally(() => alive && setRefreshing(false));
    return () => {
      alive = false;
    };
  }, [reloadKey]);

  if (error) {
    return (
      <ErrorState
        message={error}
        onRetry={() => {
          setError(null);
          setReloadKey((k) => k + 1);
        }}
      />
    );
  }
  if (!data) return <Loading label="LOADING DASHBOARD…" />;

  const { stats, analytics, recent_tracks: recent } = data;
  const totalTracks = analytics?.total_tracks ?? stats.tracks.total;

  return (
    <div className="flex flex-col gap-4">
      {totalTracks === 0 ? (
        <section className="panel relative overflow-hidden">
          <div className="grid gap-4 p-5 sm:p-6">
            <div>
              <h1 className="text-[26px] leading-[1.1] text-heading sm:text-[32px]">
                Every key, knob and cue{" "}
                <span style={{ color: "var(--color-accent)" }}>
                  in one console.
                </span>
              </h1>
              <p className="mt-2.5 max-w-xl text-[13px] leading-relaxed text-ink-dim">
                Seven workspaces on a single dark grid: dig with three search modes,
                plot harmony on the Camelot wheel, audit mixes, and keep the deck
                one keystroke away.
              </p>
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <Link to="/pipeline" className="btn btn-primary">
                  Open Pipeline
                </Link>
                <Link to="/dig" className="btn">
                  Start digging
                </Link>
              </div>
            </div>
          </div>
        </section>
      ) : (
        <section className="panel flex flex-wrap items-center justify-between gap-3 px-4 py-3.5 sm:px-5">
          <div className="min-w-0">
            <h1 className="text-xl font-bold tracking-[-0.02em] text-heading sm:text-2xl">
              Set command center
            </h1>
            <p className="font-num mt-0.5 text-[11px] text-ink-dim">
              {fmtCount(totalTracks)} tracks · {fmtCount(stats.tracks.embedded)} indexed ·{" "}
              {fmtCount(stats.sets.total)} sets · Seven workspaces
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Link to="/dig" className="btn btn-primary">
              Start digging
            </Link>
            <Link to="/builder" className="btn">
              Set Builder
            </Link>
          </div>
        </section>
      )}

      {active && job ? (
        <div
          className="panel flex flex-wrap items-center justify-between gap-3 border-accent/40 bg-accent/[0.06] px-3.5 py-2.5"
          role="status"
        >
          <p className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.14em] text-accent">
            <span className="h-1.5 w-1.5 rounded-full bg-accent" aria-hidden />
            Job running — {job.kind}
          </p>
          <p className="font-mono text-[10px] text-ink-dim">
            {job.stage} {job.total ? `(${job.processed}/${job.total})` : ""}
          </p>
        </div>
      ) : null}

      <div id="console" className="flex scroll-mt-16 flex-col gap-2.5">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <p className="eyebrow">Primary instruments</p>
          <Link
            to="/dig"
            className="inline-flex min-h-7 items-center font-mono text-[9px] uppercase tracking-[0.14em] text-ink-dim underline-offset-4 hover:text-heading hover:underline"
          >
            Open Dig →
          </Link>
        </div>
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)_minmax(0,0.95fr)]">
          <CamelotWheel keys={analytics?.top_keys ?? []} />
          <BpmHistogram buckets={analytics?.bpm_buckets ?? []} />
          <TopGenres genres={analytics?.genres ?? []} />
        </div>
      </div>

      <section className="panel overflow-hidden" aria-label="Library overview">
        <div className="flex items-center justify-between gap-3 px-3.5 py-2.5">
          <p className="eyebrow">Library overview</p>
          <button
            type="button"
            className="btn btn-ghost !min-h-0 px-2.5 py-1.5 font-mono text-[10px]"
            onClick={() => setReloadKey((k) => k + 1)}
            disabled={refreshing}
          >
            <RefreshCw size={12} className={refreshing ? "animate-spin" : undefined} />
            {refreshing ? "REFRESHING" : "REFRESH"}
          </button>
        </div>
        <div className="grid grid-cols-2 gap-px border-t border-line bg-line sm:grid-cols-4 lg:grid-cols-8">
          {KPIS.map((kpi) => (
            <div key={kpi.label} className="bg-panel px-3 py-3">
              <p className="eyebrow !text-[8.5px]">{kpi.label}</p>
              <p
                className="font-num mt-1.5 text-[21px] leading-none text-heading"
                data-kpi={kpi.label}
              >
                {fmtCount(kpi.value(data))}
              </p>
              {kpi.sub ? (
                <p className="mt-1.5 truncate text-[10px] leading-tight text-ink-faint">
                  {kpi.sub(data)}
                </p>
              ) : null}
            </div>
          ))}
        </div>
      </section>

      <TopPicks />

      <section className="panel">
        <PanelHead
          title="RECENTLY INDEXED"
          right={
            <Link to="/dig" className="btn btn-ghost !min-h-0 py-1.5">
              Open Dig
            </Link>
          }
        />
        {recent.length === 0 ? (
          <EmptyState
            title="Nothing indexed yet"
            hint="Run the Pipeline jobs to build your catalog."
          />
        ) : (
          <div className="border-t border-line px-2 py-2">
            {recent.slice(0, 12).map((t) => (
              <TrackRow key={t.id} track={t} queue={recent} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
