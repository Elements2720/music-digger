import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowDown, ChevronLeft, ChevronRight } from "lucide-react";
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

// ------------------------------------------------------------- keyboard

const SHORTCUTS = [
  { keys: ["Space"], action: "Play / pause the deck" },
  { keys: ["M"], action: "Mute or unmute" },
  { keys: ["C"], action: "Open the Set Crate" },
  { keys: ["Shift", "←"], action: "Jump to the dashboard" },
  { keys: ["Shift", "→"], action: "Jump to the pipeline" },
];

function ShortcutLegend() {
  return (
    <div className="panel overflow-hidden">
      <div className="panel-head">
        <span className="eyebrow">Keyboard legend</span>
        <span className="font-mono text-[9px] uppercase tracking-[0.14em] text-ink-faint">
          {String(SHORTCUTS.length).padStart(2, "0")} bindings
        </span>
      </div>
      <dl>
        {SHORTCUTS.map((s) => (
          <div
            key={s.action}
            className="flex items-center justify-between gap-3 border-b border-line px-3 py-2 last:border-b-0"
          >
            <dt className="flex items-center gap-1">
              {s.keys.map((k) => (
                <kbd key={k} className="shortcut-key">
                  {k}
                </kbd>
              ))}
            </dt>
            <dd className="text-right text-[11px] leading-tight text-ink-dim">
              {s.action}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

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
  const real = keys.filter((k) => k.camelot_key);
  const max = real.length ? Math.max(...real.map((k) => k.track_count)) : 0;
  const total = real.reduce((sum, k) => sum + k.track_count, 0);
  const countFor = (key: string) =>
    real.find((k) => k.camelot_key === key)?.track_count ?? 0;

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
                ].map(({ key, ring, name }) => {
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
                      tabIndex={0}
                      aria-label={`Dig ${key} ${name}, ${count} tracks`}
                      onClick={() =>
                        navigate(`/dig?mode=vibe&camelot=${key}`)
                      }
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          navigate(`/dig?mode=vibe&camelot=${key}`);
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

function bpmLabelToRange(label: string): { min: number; max: number } | null {
  const under = /^<\s*(\d+)$/.exec(label);
  if (under) return { min: 0, max: Number(under[1]) - 1 };
  const over = /^(\d+)\+$/.exec(label);
  if (over) return { min: Number(over[1]), max: 200 };
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
              const to = range
                ? `/dig?mode=vibe&bpm_min=${range.min}&bpm_max=${range.max}`
                : null;
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

// ----------------------------------------------------------- dashboard

const KPIS = [
  ["CATALOG", (d: DashboardResponse) => d.analytics?.total_tracks ?? d.stats.tracks.total],
  ["EMBEDDED", (d: DashboardResponse) => d.analytics?.total_embedded ?? d.stats.tracks.embedded],
  ["ARTISTS", (d: DashboardResponse) => d.analytics?.total_artists ?? 0],
  ["LOCAL FILES", (d: DashboardResponse) => d.analytics?.total_local ?? 0],
  ["SEEDS", (d: DashboardResponse) => d.stats.seeds.total],
  ["DJ SETS", (d: DashboardResponse) => d.stats.sets.total],
] as const;

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
  const totalTracks = analytics?.total_tracks ?? stats.tracks.total;

  return (
    <div className="flex flex-col gap-4">
      <section className="panel relative overflow-hidden">
        <span
          aria-hidden
          className="absolute inset-x-0 top-0 h-px"
          style={{
            background:
              "linear-gradient(90deg, var(--color-accent), transparent 55%)",
          }}
        />
        <div className="grid gap-5 p-5 sm:p-6 lg:grid-cols-[minmax(0,1.45fr)_minmax(280px,1fr)] lg:items-center lg:gap-8">
          <div>
            <p className="flex items-center gap-2 font-mono text-[9px] uppercase tracking-[0.2em] text-ink-faint">
              <span
                aria-hidden
                className="h-1.5 w-1.5"
                style={{ background: "var(--color-accent)" }}
              />
              DigDeeper — Set command center
            </p>
            <h1 className="mt-2.5 text-[27px] leading-[1.08] text-heading sm:text-[34px]">
              Every key, knob and cue{" "}
              <span style={{ color: "var(--color-accent)" }}>
                in one console.
              </span>
            </h1>
            <p className="mt-3 max-w-xl text-[13px] leading-relaxed text-ink-dim">
              Six workspaces on a single dark grid: dig with three search modes,
              plot harmony on the Camelot wheel, audit mixes, and keep the deck
              one keystroke away.
            </p>
            <div className="mt-5 flex flex-wrap items-center gap-2">
              <a href="#console" className="btn btn-primary">
                Open the dashboard
                <ArrowDown size={13} />
              </a>
              <Link to="/dig" className="btn">
                Start digging
              </Link>
              <span className="ml-1 hidden font-mono text-[9px] uppercase tracking-[0.14em] text-ink-faint sm:inline">
                {fmtCount(totalTracks)} tracks on disk
              </span>
            </div>
          </div>
          <ShortcutLegend />
        </div>
      </section>

      {active && job ? (
        <div
          className="panel flex flex-wrap items-center justify-between gap-3 px-3.5 py-2.5"
          role="status"
          style={{ borderLeft: "2px solid var(--color-accent)" }}
        >
          <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-accent">
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
            className="font-mono text-[9px] uppercase tracking-[0.14em] text-ink-dim underline-offset-4 hover:text-heading hover:underline"
          >
            Open Dig →
          </Link>
        </div>
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,0.92fr)_minmax(0,1.08fr)]">
          <CamelotWheel keys={analytics?.top_keys ?? []} />
          <BpmHistogram buckets={analytics?.bpm_buckets ?? []} />
        </div>
      </div>

      <section
        className="panel grid grid-cols-2 gap-px overflow-hidden bg-line sm:grid-cols-3 lg:grid-cols-6"
        aria-label="Catalog readouts"
      >
        {KPIS.map(([label, read]) => (
          <div key={label} className="bg-panel px-3.5 py-3">
            <p className="eyebrow !text-[9px]">{label}</p>
            <p
              className="font-num mt-1.5 text-[22px] leading-none text-heading"
              data-kpi={label}
            >
              {fmtCount(read(data))}
            </p>
          </div>
        ))}
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
