import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AudioWaveform, Radio, Search } from "lucide-react";
import { api } from "../api/client";
import type {
  PassagePayload,
  SetDetailResponse,
  SetsListResponse,
} from "../types/apiTypes";
import {
  EmptyState,
  ErrorState,
  KeyPill,
  Loading,
  PanelHead,
  TrackRow,
} from "../components/ui";
import { fmtBpm, fmtClock, fmtPercent, normalizePct } from "../lib/format";
import { useJobsStore } from "../stores/jobsStore";
import { useSettingsStore } from "../stores/settingsStore";

type DetailView = "tracklist" | "tracks" | "sets";

function Timeline({ passages }: { passages: PassagePayload[] }) {
  const total = Math.max(...passages.map((p) => p.end_seconds), 1);
  return (
    <div className="panel">
      <PanelHead
        title="TIMELINE"
        right={
          <div className="flex flex-wrap items-center gap-3 font-mono text-[9px] uppercase tracking-[0.1em] text-ink-faint">
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-[1px]" style={{ background: "var(--color-accent)" }} aria-hidden />
              130+ BPM
            </span>
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-[1px]" style={{ background: "var(--color-info)" }} aria-hidden />
              120–129
            </span>
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-[1px]" style={{ background: "var(--color-warn)" }} aria-hidden />
              &lt;120
            </span>
          </div>
        }
      />
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
              style={{
                left: `${left}%`,
                width: `${Math.max(0.5, width)}%`,
                background: color,
                opacity: 0.75,
              }}
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

const VIEW_TABS: { id: DetailView; label: string }[] = [
  { id: "tracklist", label: "TRACKLIST" },
  { id: "tracks", label: "SIMILAR TRACKS" },
  { id: "sets", label: "SIMILAR SETS" },
];

export function MixView() {
  const [sets, setSets] = useState<SetsListResponse | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<SetDetailResponse | null>(null);
  const [view, setView] = useState<DetailView>("tracklist");
  const [bpmTolerance, setBpmTolerance] = useState(6);
  const [genre, setGenre] = useState("");
  const [excludeHeard, setExcludeHeard] = useState(
    () => useSettingsStore.getState().hideHeard,
  );
  const [limit, setLimit] = useState(20);
  const [q, setQ] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showAnalyze, setShowAnalyze] = useState(false);
  const [source, setSource] = useState("");
  const [shazam, setShazam] = useState(true);
  const [comments, setComments] = useState(true);
  const [keepAudio, setKeepAudio] = useState(false);
  const [cookiesFile, setCookiesFile] = useState("");
  const [cookiesBrowser, setCookiesBrowser] = useState("");
  const [openMatches, setOpenMatches] = useState<Set<number>>(new Set());

  const job = useJobsStore((s) => s.job);
  const active = useJobsStore((s) => s.active);
  const startJob = useJobsStore((s) => s.start);

  const refresh = useCallback(() => {
    api
      .listSets(50)
      .then((res) => {
        setSets(res);
        setSelectedId((current) => current ?? res.sets[0]?.id ?? null);
      })
      .catch((err: unknown) => err instanceof Error && setError(err.message));
  }, []);

  useEffect(refresh, [refresh]);

  useEffect(() => {
    if (!selectedId) return;
    let alive = true;
    setBusy(true);
    api
      .setDetail(selectedId, {
        view,
        limit,
        bpm_tolerance: bpmTolerance,
        exclude_heard: excludeHeard || undefined,
        genre: genre.trim() || undefined,
      })
      .then((res) => alive && setDetail(res))
      .catch((err: unknown) => {
        if (alive && err instanceof Error) setError(err.message);
      })
      .finally(() => alive && setBusy(false));
    return () => {
      alive = false;
    };
  }, [selectedId, view, limit, bpmTolerance, excludeHeard, genre]);

  const analyze = async () => {
    if (!source.trim()) return;
    try {
      await startJob("analyze-set", {
        source: source.trim(),
        shazam,
        comments,
        keep_audio: keepAudio,
        cookies_file: cookiesFile.trim() || null,
        cookies_from_browser: cookiesBrowser.trim() || null,
      });
      setError(null);
      setShowAnalyze(false);
      setSource("");
    } catch (err) {
      if (err instanceof Error) setError(err.message);
    }
  };

  const visibleSets = (sets?.sets ?? []).filter((s) =>
    q.trim() ? `${s.artist} ${s.title}`.toLowerCase().includes(q.trim().toLowerCase()) : true,
  );
  const selected = sets?.sets.find((s) => s.id === selectedId) ?? null;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h1 className="text-2xl font-bold tracking-[-0.02em] text-heading">Mix Analyzer</h1>
        <button
          type="button"
          className="btn btn-primary"
          aria-expanded={showAnalyze}
          onClick={() => setShowAnalyze((v) => !v)}
        >
          <AudioWaveform size={14} /> ANALYZE A SET
        </button>
      </div>

      {showAnalyze ? (
        <form
          className="panel p-3"
          onSubmit={(e) => {
            e.preventDefault();
            void analyze();
          }}
        >
          <p className="eyebrow mb-2">ANALYZE A SET — URL OR LOCAL FILE</p>
          <input
            className="input"
            placeholder="https://www.youtube.com/watch?v=… or D:\sets\set.mp3"
            value={source}
            onChange={(e) => setSource(e.target.value)}
            aria-label="DJ set source URL"
          />
          <div className="mt-3 flex flex-col gap-2">
            <label className="flex items-center gap-2 font-mono text-[11px] uppercase text-ink-dim">
              <input
                type="checkbox"
                checked={shazam}
                onChange={(e) => setShazam(e.target.checked)}
                className="h-4 w-4 accent-accent"
              />
              SHAZAM UNIDENTIFIED PASSAGES
            </label>
            <label className="flex items-center gap-2 font-mono text-[11px] uppercase text-ink-dim">
              <input
                type="checkbox"
                checked={comments}
                onChange={(e) => setComments(e.target.checked)}
                className="h-4 w-4 accent-accent"
              />
              PARSE TRACKLIST FROM COMMENTS
            </label>
            <label className="flex items-center gap-2 font-mono text-[11px] uppercase text-ink-dim">
              <input
                type="checkbox"
                checked={keepAudio}
                onChange={(e) => setKeepAudio(e.target.checked)}
                className="h-4 w-4 accent-accent"
              />
              KEEP DOWNLOADED AUDIO
            </label>
          </div>
          <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
            <label className="font-mono text-[10px] uppercase text-ink-dim">
              COOKIES.TXT (OPTIONAL)
              <input
                className="input mt-1"
                placeholder="C:\path\cookies.txt"
                value={cookiesFile}
                onChange={(e) => setCookiesFile(e.target.value)}
                aria-label="Cookies file path"
              />
            </label>
            <label className="font-mono text-[10px] uppercase text-ink-dim">
              COOKIES FROM BROWSER (OPTIONAL)
              <input
                className="input mt-1"
                placeholder="firefox, edge, chrome…"
                value={cookiesBrowser}
                onChange={(e) => setCookiesBrowser(e.target.value)}
                aria-label="Cookies from browser"
              />
            </label>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <button type="submit" className="btn btn-primary" disabled={!source.trim()}>
              ANALYZE
            </button>
            <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-ink-faint">
              progress opens in Pipeline
            </span>
          </div>
        </form>
      ) : null}

      {active && job ? (
        <div className="panel p-3" role="status">
          <p className="eyebrow text-accent">ANALYSIS RUNNING — {job.kind}</p>
          <p className="mt-1 text-xs text-ink-dim">
            {job.stage} {job.total ? `(${job.processed}/${job.total})` : ""}
          </p>
        </div>
      ) : null}

      {error ? (
        <ErrorState
          message={error}
          onRetry={() => {
            setError(null);
            refresh();
          }}
        />
      ) : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[300px_minmax(0,1fr)]">
        <section className="panel self-start">
          <div className="panel-head">
            <span className="eyebrow">STORED SETS</span>
            <span className="flex items-center gap-2">
              <span className="pill font-num">{sets?.sets.length ?? 0}</span>
              <button
                type="button"
                className="btn btn-ghost !min-h-7 px-2.5 py-1 font-mono text-[9px]"
                onClick={refresh}
              >
                REFRESH
              </button>
            </span>
          </div>
          <div className="px-3 py-2">
            <div className="input-icon-wrap">
              <Search
                size={14}
                aria-hidden
              />
              <input
                className="input"
                placeholder="Filter sets…"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                aria-label="Filter sets"
              />
            </div>
          </div>
          {!sets ? (
            <Loading />
          ) : visibleSets.length === 0 ? (
            <p className="px-3 pb-3 text-sm text-ink-dim">
              No sets yet — paste a URL above to analyze one.
            </p>
          ) : (
            <ul className="scroll-thin max-h-[460px] divide-y divide-line overflow-y-auto">
              {visibleSets.map((s) => (
                <li key={s.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedId(s.id)}
                    aria-current={s.id === selectedId}
                    className={`flex w-full items-center gap-3 px-3 py-2 text-left transition-colors hover:bg-fill ${
                      s.id === selectedId ? "bg-fill" : ""
                    }`}
                  >
                    <Radio
                      size={15}
                      className={s.id === selectedId ? "text-accent" : "text-ink-faint"}
                      aria-hidden
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm text-heading">{s.title}</span>
                      <span className="font-num block text-[11px] text-ink-dim">
                        {s.artist || "unknown"} · {s.passage_count} passages
                        {s.bpm_min != null && s.bpm_max != null
                          ? ` · ${fmtBpm(s.bpm_min)}–${fmtBpm(s.bpm_max)} BPM`
                          : ""}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="flex min-w-0 flex-col gap-3">
          {!selected ? (
            <EmptyState title="NO SET SELECTED" hint="Pick a set to inspect its passages." />
          ) : (
            <>
              <div className="panel flex flex-wrap items-center gap-3 p-3">
                <button
                  type="button"
                  className="btn btn-ghost !min-h-0 px-2 py-1.5 font-mono text-[9px]"
                  onClick={() => {
                    setSelectedId(null);
                    setDetail(null);
                  }}
                >
                  ← BACK
                </button>
                <div className="min-w-0 flex-1">
                  <h2 className="truncate text-lg font-semibold text-heading">{selected.title}</h2>
                  <p className="font-num text-[11px] text-ink-dim">
                    {selected.artist || "unknown artist"} · {selected.passage_count} passages ·{" "}
                    {fmtClock(selected.duration_seconds)}
                    {selected.bpm_min != null && selected.bpm_max != null
                      ? ` · ${fmtBpm(selected.bpm_min)}–${fmtBpm(selected.bpm_max)} BPM`
                      : ""}
                  </p>
                </div>
                {selected.source_url ? (
                  <a
                    className="btn !min-h-0 py-1.5"
                    href={selected.source_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    SOURCE
                  </a>
                ) : null}
                <Link className="btn !min-h-0 py-1.5" to="/dig?mode=vibe">
                  DIG
                </Link>
              </div>

              <div className="flex flex-wrap items-center gap-3 border-b border-line pb-2">
                <div role="tablist" aria-label="Set detail views" className="flex gap-4">
                  {VIEW_TABS.map((t) => (
                    <button
                      key={t.id}
                      type="button"
                      role="tab"
                      aria-selected={view === t.id}
                      onClick={() => setView(t.id)}
                      className="tab !min-h-11"
                    >
                      {t.label}
                    </button>
                  ))}
                </div>
                <label className="flex items-center gap-2 font-mono text-[10px] uppercase text-ink-dim">
                  BPM ±
                  <input
                    type="number"
                    min={0}
                    max={40}
                    className="input !min-h-0 !h-10 !w-16"
                    value={bpmTolerance}
                    onChange={(e) => setBpmTolerance(Number(e.target.value))}
                    aria-label="BPM tolerance"
                  />
                </label>
                <label className="flex items-center gap-2 font-mono text-[10px] uppercase text-ink-dim">
                  LIMIT
                  <select
                    className="input !min-h-0 !h-10 !w-auto"
                    value={limit}
                    onChange={(e) => setLimit(Number(e.target.value))}
                    aria-label="Result limit"
                  >
                    {[10, 20, 30, 50].map((n) => (
                      <option key={n} value={n}>
                        {n}
                      </option>
                    ))}
                  </select>
                </label>
                <input
                  className="input !min-h-0 !h-10 max-w-[160px]"
                  placeholder="genre"
                  value={genre}
                  onChange={(e) => setGenre(e.target.value)}
                  aria-label="Genre filter"
                />
                <label className="flex min-h-10 items-center gap-2 font-mono text-[10px] uppercase text-ink-dim">
                  <input
                    type="checkbox"
                    checked={excludeHeard}
                    onChange={(e) => setExcludeHeard(e.target.checked)}
                    className="h-4 w-4 accent-accent"
                  />
                  HIDE HEARD
                </label>
              </div>

              {busy && !detail ? <Loading label="LOADING SET…" /> : null}

              {view === "tracklist" && detail?.passages ? (
                <>
                  <Timeline passages={detail.passages} />
                  <div className="panel">
                    <PanelHead title={`PASSAGES — ${detail.passages.length}`} />
                    <div className="divide-y divide-line">
                      {detail.passages.map((p, i) => (
                        <div key={i} className="flex flex-col gap-2 px-3 py-2">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-num text-xs text-ink-faint">
                              {fmtClock(p.start_seconds)} – {fmtClock(p.end_seconds)}
                            </span>
                            {p.bpm != null ? (
                              <span className="font-num text-xs text-heading">
                                {fmtBpm(p.bpm)} BPM
                              </span>
                            ) : null}
                            <KeyPill k={p.key} />
                            {p.exact_id_title ? (
                              <span className="min-w-0 break-words text-sm text-heading">
                                {p.exact_id_artist ? `${p.exact_id_artist} — ` : ""}
                                {p.exact_id_title}
                              </span>
                            ) : (
                              <span className="text-sm italic text-ink-faint">unidentified</span>
                            )}
                            {p.exact_id_source ? (
                              <span className="pill font-mono text-[9px] lowercase text-ink-dim">
                                {p.exact_id_source}
                              </span>
                            ) : null}
                            {p.matches.length > 0 ? (
                              <button
                                type="button"
                                className="inline-flex min-h-7 items-center rounded-[4px] border border-line/70 px-2 py-0.5 font-mono text-[10px] text-ink-dim transition-colors hover:border-accent/60 hover:text-accent"
                                aria-expanded={openMatches.has(i)}
                                onClick={() =>
                                  setOpenMatches((prev) => {
                                    const next = new Set(prev);
                                    if (next.has(i)) next.delete(i);
                                    else next.add(i);
                                    return next;
                                  })
                                }
                              >
                                {openMatches.has(i) ? "▾" : "▸"} {p.matches.length} closest
                                matches
                              </button>
                            ) : null}
                          </div>
                          {openMatches.has(i)
                            ? p.matches.map((m) => (
                                <TrackRow
                                  key={m.track.id}
                                  track={m.track}
                                  queue={p.matches.map((x) => x.track)}
                                  showMatch={normalizePct(m.similarity)}
                                />
                              ))
                            : null}
                        </div>
                      ))}
                    </div>
                  </div>
                </>
              ) : null}

              {view === "tracks" && detail?.matches ? (
                detail.matches.length === 0 ? (
                  <EmptyState title="NO MATCHES" hint="Try a wider BPM tolerance." />
                ) : (
                  <div className="panel">
                    {detail.matches.map((m) => (
                      <TrackRow
                        key={m.track.id}
                        track={m.track}
                        showMatch={normalizePct(m.similarity)}
                      />
                    ))}
                  </div>
                )
              ) : null}

              {view === "sets" && detail?.sets ? (
                detail.sets.length === 0 ? (
                  <EmptyState title="NO SIMILAR SETS" hint="Analyze more sets to compare them." />
                ) : (
                  <div className="panel">
                    {detail.sets.map((s) => (
                      <button
                        key={s.set.id}
                        type="button"
                        onClick={() => setSelectedId(s.set.id)}
                        className="flex w-full items-center gap-3 border-b border-line px-3 py-2 text-left last:border-b-0 hover:bg-fill"
                      >
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm text-heading">{s.set.title}</span>
                          <span className="font-num block text-[11px] text-ink-dim">
                            {s.set.artist || "unknown"} · {fmtClock(s.set.duration_seconds)} ·{" "}
                            {s.set.passage_count} passages
                          </span>
                        </span>
                        <span className="font-num text-sm text-accent">
                          {fmtPercent(normalizePct(s.similarity))}
                        </span>
                      </button>
                    ))}
                  </div>
                )
              ) : null}
            </>
          )}
        </section>
      </div>
    </div>
  );
}
