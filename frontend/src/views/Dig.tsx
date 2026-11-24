import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Disc3, Search, Sparkles } from "lucide-react";
import { api } from "../api/client";
import type {
  DigResponse,
  TasteRankingResponse,
  Track,
  VibeSearchResponse,
} from "../types/apiTypes";
import {
  EmptyState,
  ErrorState,
  Loading,
  TrackRow,
} from "../components/ui";

type SubMode = "match" | "foryou" | "vibe";

const MODES: { id: SubMode; label: string; hint: string }[] = [
  { id: "match", label: "MATCH A TRACK", hint: "Find tracks like a seed track" },
  { id: "foryou", label: "FOR YOU", hint: "Taste-ranked from your local catalog" },
  { id: "vibe", label: "VIBE & CATALOG", hint: "CLAP text search + filters" },
];

const TASTE_MODES: { id: "both" | "local" | "liked"; label: string }[] = [
  { id: "local", label: "LOCAL" },
  { id: "liked", label: "LIKED" },
  { id: "both", label: "BOTH" },
];

const CAMELOT_KEYS = Array.from({ length: 12 }, (_, i) => `${i + 1}A`).flatMap((k) => [
  k,
  `${k.slice(0, -1)}B`,
]);

const SOURCES = ["local", "itunes", "deezer"] as const;

/** Backend similarity is 0-100; older payloads may still be 0-1. Never *100 twice. */
export function normalizePct(n: number): number {
  const pct = n > 0 && n <= 1 ? n * 100 : n;
  return Math.round(pct);
}

export function DigView() {
  const [params, setParams] = useSearchParams();
  const mode = (params.get("mode") as SubMode) || "match";
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // match-a-track
  const [query, setQuery] = useState("");
  const [options, setOptions] = useState<Track[]>([]);
  const [searchState, setSearchState] = useState<"idle" | "error" | "empty" | "ok">(
    "idle",
  );
  const [searchMessage, setSearchMessage] = useState<string | null>(null);
  const [seed, setSeed] = useState<Track | null>(null);
  const [digResult, setDigResult] = useState<DigResponse | null>(null);
  const [harmonic, setHarmonic] = useState(true);
  const [bpmTolerance, setBpmTolerance] = useState(4);
  // seed preloaded from a deep link (?mode=match&seed=<id>) — runs once per seed
  const seedRequested = useRef<string | null>(null);

  // for you
  const [tasteMode, setTasteMode] = useState<"both" | "local" | "liked">("local");
  const [taste, setTaste] = useState<TasteRankingResponse | null>(null);

  // vibe
  const [vibeQuery, setVibeQuery] = useState("");
  const [vibeResult, setVibeResult] = useState<VibeSearchResponse | null>(null);
  const [filterKey, setFilterKey] = useState("");
  const [filterBpmMin, setFilterBpmMin] = useState("");
  const [filterBpmMax, setFilterBpmMax] = useState("");
  const [filterSource, setFilterSource] = useState("");
  const [filterResult, setFilterResult] = useState<Track[] | null>(null);
  const camelotRequested = useRef<string | null>(null);

  const setMode = (m: SubMode) => {
    const next = new URLSearchParams(params);
    next.set("mode", m);
    setParams(next, { replace: true });
  };

  useEffect(() => {
    if (mode !== "foryou") return;
    let alive = true;
    setBusy(true);
    setError(null);
    api
      .tasteRanking({ mode: tasteMode, limit: 30 })
      .then((res) => alive && setTaste(res))
      .catch((err: unknown) => {
        if (alive && err instanceof Error) setError(err.message);
      })
      .finally(() => setBusy(false));
    return () => {
      alive = false;
    };
  }, [mode, tasteMode]);

  const search = useCallback(async (q: string) => {
    if (q.trim().length < 2) {
      setOptions([]);
      setSearchState("idle");
      setSearchMessage(null);
      return;
    }
    setSearchMessage(null);
    try {
      const res = await api.searchTracks(q, 8);
      setOptions(res.tracks);
      setSearchState(res.tracks.length === 0 ? "empty" : "ok");
    } catch (err) {
      setOptions([]);
      setSearchState("error");
      setSearchMessage(err instanceof Error ? err.message : "Search failed");
    }
  }, []);

  useEffect(() => {
    const t = window.setTimeout(() => void search(query), 250);
    return () => window.clearTimeout(t);
  }, [query, search]);

  const runDig = async (track: Track) => {
    setSeed(track);
    setOptions([]);
    setQuery("");
    setSearchState("idle");
    setBusy(true);
    setError(null);
    try {
      const res = await api.dig(track.id, {
        limit: 20,
        bpm_tolerance: bpmTolerance,
        harmonic,
      });
      setDigResult(res);
    } catch (err) {
      if (err instanceof Error) setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  // Deep link: /dig?mode=match&seed=<track id> — load the seed and dig it once.
  const seedParam = params.get("seed");
  useEffect(() => {
    if (mode !== "match" || !seedParam || seedRequested.current === seedParam)
      return;
    seedRequested.current = seedParam;
    let alive = true;
    setBusy(true);
    setError(null);
    api
      .dig(seedParam, { limit: 20, bpm_tolerance: bpmTolerance, harmonic })
      .then((res) => {
        if (!alive) return;
        setSeed(res.reference);
        setDigResult(res);
      })
      .catch((err: unknown) => {
        if (alive && err instanceof Error) setError(err.message);
      })
      .finally(() => {
        if (alive) setBusy(false);
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, seedParam]);

  const runVibe = async () => {
    setBusy(true);
    setError(null);
    try {
      if (vibeQuery.trim()) {
        const res = await api.vibeSearch({ query: vibeQuery, limit: 30 });
        setVibeResult(res);
        setFilterResult(null);
      } else {
        const res = await api.filterCatalog({
          key: filterKey || undefined,
          bpm_min: filterBpmMin ? Number(filterBpmMin) : undefined,
          bpm_max: filterBpmMax ? Number(filterBpmMax) : undefined,
          source: filterSource || undefined,
          limit: 60,
        });
        setFilterResult(res.tracks);
        setVibeResult(null);
      }
    } catch (err) {
      if (err instanceof Error) setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  // Deep link: /dig?mode=vibe&camelot=12A — prefill the key and run immediately.
  const camelotParam = params.get("camelot");
  useEffect(() => {
    if (
      mode !== "vibe" ||
      !camelotParam ||
      camelotRequested.current === camelotParam
    )
      return;
    camelotRequested.current = camelotParam;
    let alive = true;
    setFilterKey(camelotParam);
    setBusy(true);
    setError(null);
    api
      .filterCatalog({ key: camelotParam, limit: 60 })
      .then((res) => alive && setFilterResult(res.tracks))
      .catch((err: unknown) => {
        if (alive && err instanceof Error) setError(err.message);
      })
      .finally(() => {
        if (alive) setBusy(false);
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, camelotParam]);

  const modeHint = useMemo(
    () => MODES.find((m) => m.id === mode)?.hint ?? "",
    [mode],
  );

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-bold tracking-[-0.02em] text-heading">Dig</h1>
        <p className="mt-1 text-sm text-ink-dim">{modeHint}</p>
      </div>

      <div
        role="tablist"
        aria-label="Dig modes"
        className="flex flex-wrap gap-2"
        data-testid="dig-modes"
      >
        {MODES.map((m) => (
          <button
            key={m.id}
            type="button"
            role="tab"
            aria-selected={mode === m.id}
            onClick={() => setMode(m.id)}
            className="btn !min-h-0 py-2"
            style={
              mode === m.id
                ? { borderColor: "var(--color-accent)", color: "var(--color-accent)" }
                : undefined
            }
          >
            {m.id === "match" ? <Disc3 size={14} /> : m.id === "foryou" ? <Sparkles size={14} /> : <Search size={14} />}
            {m.label}
          </button>
        ))}
      </div>

      {error ? <ErrorState message={error} /> : null}

      {mode === "match" ? (
        <section className="flex flex-col gap-3">
          <div className="panel p-4">
            <label htmlFor="dig-search" className="eyebrow mb-2 block">
              SEED TRACK
            </label>
            <input
              id="dig-search"
              className="input"
              placeholder="Search your catalog by title or artist…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              autoComplete="off"
            />
            {searchState === "error" ? (
              <p
                className="mt-2 font-mono text-[11px] uppercase tracking-[0.1em]"
                style={{ color: "var(--color-warn)" }}
                role="status"
              >
                SEARCH FAILED — {searchMessage ?? "try again"}
              </p>
            ) : searchState === "empty" ? (
              <p
                className="mt-2 font-mono text-[11px] uppercase tracking-[0.1em] text-ink-faint"
                role="status"
              >
                NO TRACKS FOUND
              </p>
            ) : null}
            {options.length > 0 ? (
              <ul className="mt-2 divide-y divide-line border border-line">
                {options.map((t) => (
                  <li key={t.id}>
                    <button
                      type="button"
                      className="w-full px-3 py-2 text-left hover:bg-panel-2"
                      onClick={() => void runDig(t)}
                    >
                      <span className="block truncate text-sm text-heading">{t.title}</span>
                      <span className="block truncate text-xs text-ink-dim">{t.artist}</span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
            <div className="mt-3 flex flex-wrap items-center gap-4">
              <label className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.1em] text-ink-dim">
                <input
                  type="checkbox"
                  checked={harmonic}
                  onChange={(e) => setHarmonic(e.target.checked)}
                  className="h-4 w-4 accent-accent"
                />
                HARMONIC
              </label>
              <label className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.1em] text-ink-dim">
                BPM ±{bpmTolerance}
                <input
                  type="range"
                  min={0}
                  max={10}
                  value={bpmTolerance}
                  onChange={(e) => setBpmTolerance(Number(e.target.value))}
                  className="w-32 accent-accent"
                  aria-label="BPM tolerance"
                />
              </label>
            </div>
          </div>

          {seed ? (
            <p className="eyebrow">
              SEED — {seed.artist} / {seed.title}
            </p>
          ) : null}
          {busy ? <Loading label="DIGGING…" /> : null}
          {digResult ? (
            digResult.matches.length === 0 ? (
              <EmptyState
                title="NO MATCHES"
                hint="Widen the BPM tolerance or turn off harmonic filtering."
              />
            ) : (
              <div className="panel">
                {digResult.matches.map((m) => (
                  <TrackRow
                    key={m.track.id}
                    track={m.track}
                    queue={digResult.matches.map((x) => x.track)}
                    showMatch={normalizePct(m.similarity)}
                  />
                ))}
              </div>
            )
          ) : null}
        </section>
      ) : null}

      {mode === "foryou" ? (
        <section className="flex flex-col gap-3">
          <div
            role="tablist"
            aria-label="Taste mode"
            className="flex gap-2"
            data-testid="taste-modes"
          >
            {TASTE_MODES.map((m) => (
              <button
                key={m.id}
                type="button"
                role="tab"
                aria-selected={tasteMode === m.id}
                onClick={() => setTasteMode(m.id)}
                className="btn !min-h-0 py-2"
                style={
                  tasteMode === m.id
                    ? { borderColor: "var(--color-accent)", color: "var(--color-accent)" }
                    : undefined
                }
              >
                {m.label}
              </button>
            ))}
          </div>
          {busy && !taste ? <Loading label="RANKING YOUR TASTE…" /> : null}
          {taste ? (
            taste.matches.length === 0 ? (
              <EmptyState
                title="NOTHING RANKED YET"
                hint="Taste ranking needs embedded local tracks (and liked artists for LIKED mode). Run the index job first."
              />
            ) : (
              <div className="panel" data-testid="taste-results">
                {taste.matches.map((m, i) => (
                  <TrackRow
                    key={m.id}
                    track={m}
                    index={i}
                    queue={taste.matches}
                    showMatch={normalizePct(m.taste_percent)}
                  />
                ))}
              </div>
            )
          ) : null}
        </section>
      ) : null}

      {mode === "vibe" ? (
        <section className="flex flex-col gap-3" data-testid="vibe-panel">
          <form
            className="panel flex flex-col gap-3 p-4"
            onSubmit={(e) => {
              e.preventDefault();
              void runVibe();
            }}
          >
            <div className="flex gap-2">
              <input
                className="input flex-1"
                placeholder="Describe the vibe — e.g. rolling melodic techno after midnight"
                value={vibeQuery}
                onChange={(e) => setVibeQuery(e.target.value)}
                aria-label="Vibe query"
              />
              <button type="submit" className="btn btn-primary" disabled={busy}>
                {busy ? "SEARCHING…" : "SEARCH"}
              </button>
            </div>

            <fieldset className="flex flex-wrap items-end gap-3 border-t border-line pt-3">
              <legend className="eyebrow mb-1">CATALOG FILTERS</legend>
              <label className="flex flex-col gap-1 font-mono text-[10px] uppercase tracking-[0.1em] text-ink-dim">
                CAMELOT KEY
                <select
                  className="input !w-auto font-num"
                  value={filterKey}
                  onChange={(e) => setFilterKey(e.target.value)}
                  aria-label="Camelot key filter"
                >
                  <option value="">ANY</option>
                  {CAMELOT_KEYS.map((k) => (
                    <option key={k} value={k}>
                      {k}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1 font-mono text-[10px] uppercase tracking-[0.1em] text-ink-dim">
                BPM MIN
                <input
                  className="input !w-20 font-num"
                  type="number"
                  inputMode="numeric"
                  min={0}
                  max={200}
                  value={filterBpmMin}
                  onChange={(e) => setFilterBpmMin(e.target.value)}
                  aria-label="BPM minimum"
                />
              </label>
              <label className="flex flex-col gap-1 font-mono text-[10px] uppercase tracking-[0.1em] text-ink-dim">
                BPM MAX
                <input
                  className="input !w-20 font-num"
                  type="number"
                  inputMode="numeric"
                  min={0}
                  max={200}
                  value={filterBpmMax}
                  onChange={(e) => setFilterBpmMax(e.target.value)}
                  aria-label="BPM maximum"
                />
              </label>
              <label className="flex flex-col gap-1 font-mono text-[10px] uppercase tracking-[0.1em] text-ink-dim">
                SOURCE
                <select
                  className="input !w-auto"
                  value={filterSource}
                  onChange={(e) => setFilterSource(e.target.value)}
                  aria-label="Source filter"
                >
                  <option value="">ANY</option>
                  {SOURCES.map((s) => (
                    <option key={s} value={s}>
                      {s.toUpperCase()}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                className="btn !min-h-0 py-2 font-mono text-[10px]"
                onClick={() => {
                  setFilterKey("");
                  setFilterBpmMin("");
                  setFilterBpmMax("");
                  setFilterSource("");
                  setFilterResult(null);
                }}
              >
                RESET
              </button>
              <p className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-faint">
                Leave the vibe query empty to filter the catalog directly.
              </p>
            </fieldset>
          </form>
          {filterResult ? (
            filterResult.length === 0 ? (
              <EmptyState
                title="NO TRACKS MATCH"
                hint="Loosen the key, BPM range or source filters."
              />
            ) : (
              <div className="panel" data-testid="filter-results">
                {filterResult.map((t, i) => (
                  <TrackRow
                    key={t.id}
                    track={t}
                    index={i}
                    queue={filterResult}
                  />
                ))}
              </div>
            )
          ) : vibeResult ? (
            vibeResult.matches.length === 0 ? (
              <EmptyState title="NO RESULTS" hint="Try a different description." />
            ) : (
              <div className="panel">
                {vibeResult.matches.map((m) => (
                  <TrackRow
                    key={m.track.id}
                    track={m.track}
                    queue={vibeResult.matches.map((x) => x.track)}
                    showMatch={normalizePct(m.similarity)}
                  />
                ))}
              </div>
            )
          ) : (
            <EmptyState
              title="VIBE SEARCH"
              hint="Semantic CLAP search over your embedded catalog. Describe a mood, energy or scene — or use the catalog filters below."
            />
          )}
        </section>
      ) : null}
    </div>
  );
}
