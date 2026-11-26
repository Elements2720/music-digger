import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Disc3, Search, Sparkles, X } from "lucide-react";
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
import { DigSeedPanel } from "../components/DigSeedPanel";
import { SeedCard } from "../components/SeedCard";
import { useDigTrailStore } from "../stores/digTrailStore";
import { useActiveProfile, useSettingsStore } from "../stores/settingsStore";
import { normalizePct } from "../lib/format";

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

export function DigView() {
  const [params, setParams] = useSearchParams();
  const rawMode = params.get("mode");
  const mode: SubMode =
    rawMode === "match" || rawMode === "foryou" || rawMode === "vibe"
      ? rawMode
      : "match";
  const artistParam = params.get("artist")?.trim() ?? "";
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // match-a-track
  const seeds = useDigTrailStore((s) => s.seeds);
  const activeId = useDigTrailStore((s) => s.activeId);
  const pushSeed = useDigTrailStore((s) => s.push);
  const setActiveSeed = useDigTrailStore((s) => s.setActive);
  const source = useDigTrailStore((s) => s.source);
  const setSource = useDigTrailStore((s) => s.setSource);
  const activeSeed = useMemo(
    () => seeds.find((t) => t.id === activeId) ?? null,
    [seeds, activeId],
  );
  const [digResult, setDigResult] = useState<DigResponse | null>(null);
  const profile = useActiveProfile();
  const profiles = useSettingsStore((s) => s.profiles);
  const setActiveProfile = useSettingsStore((s) => s.setActiveProfile);
  const maxPerArtist = useSettingsStore((s) => s.maxPerArtist);
  const hideHeard = useSettingsStore((s) => s.hideHeard);
  const excludeLocal = useSettingsStore((s) => s.excludeLocal);
  const harmonicMode = useSettingsStore((s) => s.harmonicMode);
  const [harmonic, setHarmonic] = useState(() => useSettingsStore.getState().defaultHarmonic);
  const [bpmToleranceInput, setBpmToleranceInput] = useState(() =>
    String(useSettingsStore.getState().defaultBpmTolerance),
  );
  const [limitInput, setLimitInput] = useState(() => String(profile?.defaultLimit ?? 20));
  const [digGenre, setDigGenre] = useState(profile?.genre ?? "");
  const [digMinYear, setDigMinYear] = useState("");
  const [excludeHeard, setExcludeHeard] = useState(
    () => useSettingsStore.getState().hideHeard,
  );
  const [digNonce, setDigNonce] = useState(0);
  const bpmTolerance = useMemo(() => {
    const n = Number(bpmToleranceInput);
    return bpmToleranceInput.trim() === "" || !Number.isFinite(n)
      ? 6
      : Math.min(30, Math.max(0, Math.round(n)));
  }, [bpmToleranceInput]);
  const limit = useMemo(() => {
    const n = Number(limitInput);
    return limitInput.trim() === "" || !Number.isFinite(n)
      ? (profile?.defaultLimit ?? 20)
      : Math.min(200, Math.max(1, Math.round(n)));
  }, [limitInput, profile?.defaultLimit]);
  // the last dig actually requested, so a re-render never re-queries the same seed
  const fetchedKey = useRef<string | null>(null);
  // seed preloaded from a deep link (?mode=match&seed=<id>) — runs once per seed
  const seedRequested = useRef<string | null>(null);

  // for you
  const [tasteMode, setTasteMode] = useState<"both" | "local" | "liked">(
    () => profile?.defaultMode ?? "both",
  );
  const [taste, setTaste] = useState<TasteRankingResponse | null>(null);

  useEffect(() => {
    if (!profile) return;
    setTasteMode(profile.defaultMode);
    setLimitInput(String(profile.defaultLimit));
    setDigGenre(profile.genre ?? "");
  }, [profile]);

  // vibe
  const [vibeQuery, setVibeQuery] = useState("");
  const [vibeResult, setVibeResult] = useState<VibeSearchResponse | null>(null);
  const [filterKey, setFilterKey] = useState("");
  const [filterBpmMin, setFilterBpmMin] = useState("");
  const [filterBpmMax, setFilterBpmMax] = useState("");
  const [filterGenre, setFilterGenre] = useState("");
  const [filterSource, setFilterSource] = useState("");
  const [filterResult, setFilterResult] = useState<Track[] | null>(null);
  const [vibeRangeError, setVibeRangeError] = useState<string | null>(null);
  const vibeDeepLinkKey = useRef<string | null>(null);

  const setMode = (m: SubMode) => {
    // a pending match/foryou request must not bleed its busy state into the new mode
    setBusy(false);
    const next = new URLSearchParams(params);
    next.set("mode", m);
    setParams(next, { replace: true });
  };

  useEffect(() => {
    if (mode !== "foryou") return;
    let alive = true;
    setBusy(true);
    setError(null);
    const controller = new AbortController();
    api
      .tasteRanking(
        {
          mode: tasteMode,
          limit: profile?.defaultLimit ?? 30,
          genre: profile?.genre ?? undefined,
          bpm_min: profile?.bpmMin ?? undefined,
          bpm_max: profile?.bpmMax ?? undefined,
          artist: artistParam || undefined,
          liked_weight: profile?.likedWeight,
          local_weight: profile?.localWeight,
          max_per_artist: maxPerArtist,
          hide_heard: hideHeard,
          exclude_local: excludeLocal,
        },
        { signal: controller.signal },
      )
      .then((res) => alive && setTaste(res))
      .catch((err: unknown) => {
        // aborts are expected when the effect re-runs — do not surface them
        if (alive && err instanceof Error && err.name !== "AbortError")
          setError(err.message);
      })
      .finally(() => {
        if (alive) setBusy(false);
      });
    return () => {
      alive = false;
      controller.abort();
    };
  }, [mode, tasteMode, profile, artistParam, maxPerArtist, hideHeard, excludeLocal]);

  const runDig = (track: Track) => {
    setError(null);
    pushSeed(track);
  };

  const makeDigKey = (id: string) =>
    `${id}|${bpmTolerance}|${harmonic}|${limit}|${digGenre}|${digMinYear}|${excludeHeard}|${harmonicMode}|${maxPerArtist}|${digNonce}`;

  // One place fetches matches: the active trail seed, the BPM window or the
  // harmonic switch changing. Debounced so dragging the slider is one request.
  const seedId = activeSeed?.id ?? null;
  useEffect(() => {
    if (mode !== "match" || !seedId) return;
    const key = makeDigKey(seedId);
    if (fetchedKey.current === key) return;
    let alive = true;
    setBusy(true);
    setError(null);
    const timer = window.setTimeout(() => {
      fetchedKey.current = key;
      api
        .dig(seedId, {
          limit,
          bpm_tolerance: bpmTolerance,
          harmonic,
          harmonic_mode: harmonicMode,
          max_per_artist: maxPerArtist,
          genre: digGenre.trim() || undefined,
          min_year: digMinYear ? Number(digMinYear) : undefined,
          exclude_heard: excludeHeard || undefined,
        })
        .then((res) => {
          if (alive) setDigResult(res);
        })
        .catch((err: unknown) => {
          if (alive && err instanceof Error) setError(err.message);
        })
        .finally(() => {
          if (alive) setBusy(false);
        });
    }, 250);
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [
    mode,
    seedId,
    bpmTolerance,
    harmonic,
    harmonicMode,
    maxPerArtist,
    limit,
    digGenre,
    digMinYear,
    excludeHeard,
    digNonce,
  ]);

  // Deep link: /dig?mode=match&seed=<track id> — load the seed and dig it once.
  const seedParam = params.get("seed");
  useEffect(() => {
    if (mode !== "match" || !seedParam || seedRequested.current === seedParam)
      return;
    seedRequested.current = seedParam;
    if (useDigTrailStore.getState().seeds.some((t) => t.id === seedParam)) {
      setActiveSeed(seedParam);
      return;
    }
    let alive = true;
    setBusy(true);
    setError(null);
    const expectedKey = makeDigKey(seedParam);
    api
      .dig(seedParam, {
        limit,
        bpm_tolerance: bpmTolerance,
        harmonic,
        harmonic_mode: harmonicMode,
        max_per_artist: maxPerArtist,
        genre: digGenre.trim() || undefined,
        min_year: digMinYear ? Number(digMinYear) : undefined,
        exclude_heard: excludeHeard || undefined,
      })
      .then((res) => {
        if (!alive) return;
        fetchedKey.current = expectedKey;
        pushSeed(res.reference);
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
    const min = filterBpmMin ? Number(filterBpmMin) : null;
    const max = filterBpmMax ? Number(filterBpmMax) : null;
    if (min != null && max != null && min > max) {
      setVibeRangeError("BPM MIN is above BPM MAX — swap the values");
      setFilterResult(null);
      setVibeResult(null);
      return;
    }
    setVibeRangeError(null);
    setBusy(true);
    setError(null);
    try {
      if (vibeQuery.trim()) {
        const res = await api.vibeSearch({
          query: vibeQuery.trim(),
          limit: 30,
          bpm_min: min ?? undefined,
          bpm_max: max ?? undefined,
          camelot_keys: filterKey ? [filterKey] : undefined,
          exclude_heard: hideHeard || undefined,
          genre: filterGenre.trim() || undefined,
        });
        setVibeResult(res);
        setFilterResult(null);
      } else {
        const res = await api.filterCatalog({
          q: filterGenre.trim() || undefined,
          key: filterKey || undefined,
          bpm_min: min ?? undefined,
          bpm_max: max ?? undefined,
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

  // Deep links: /dig?mode=vibe&camelot=12A or &bpm_min=125&bpm_max=129 — prefill & run.
  const camelotParam = params.get("camelot");
  const bpmMinParam = params.get("bpm_min");
  const bpmMaxParam = params.get("bpm_max");
  useEffect(() => {
    if (mode !== "vibe") return;
    if (!camelotParam && !bpmMinParam && !bpmMaxParam) return;
    const reqKey = `${camelotParam ?? ""}|${bpmMinParam ?? ""}|${bpmMaxParam ?? ""}`;
    if (vibeDeepLinkKey.current === reqKey) return;
    vibeDeepLinkKey.current = reqKey;

    let alive = true;
    setFilterKey(camelotParam ?? "");
    setFilterBpmMin(bpmMinParam ?? "");
    setFilterBpmMax(bpmMaxParam ?? "");
    setVibeRangeError(null);
    setBusy(true);
    setError(null);
    api
      .filterCatalog({
        key: camelotParam || undefined,
        bpm_min: bpmMinParam ? Number(bpmMinParam) : undefined,
        bpm_max: bpmMaxParam ? Number(bpmMaxParam) : undefined,
        limit: 60,
      })
      .then((res) => {
        if (!alive) return;
        setFilterResult(res.tracks);
        setVibeResult(null);
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
  }, [mode, camelotParam, bpmMinParam, bpmMaxParam]);

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
        className="no-scrollbar flex flex-nowrap items-center gap-4 overflow-x-auto border-b border-line"
        data-testid="dig-modes"
      >
        {MODES.map((m) => (
          <button
            key={m.id}
            type="button"
            role="tab"
            aria-selected={mode === m.id}
            onClick={() => setMode(m.id)}
            className="tab shrink-0 gap-2 whitespace-nowrap"
          >
            {m.id === "match" ? <Disc3 size={14} /> : m.id === "foryou" ? <Sparkles size={14} /> : <Search size={14} />}
            {m.label}
          </button>
        ))}
      </div>

      {error ? (
        <ErrorState
          message={error}
          onRetry={() => {
            setError(null);
            if (mode === "match") setDigNonce((n) => n + 1);
            else if (mode === "vibe") void runVibe();
          }}
        />
      ) : null}

      {mode === "match" ? (
        <section
          data-testid="dig-match"
          className="grid min-w-0 grid-cols-1 items-start gap-4 lg:grid-cols-[260px_minmax(0,1fr)]"
        >
          <DigSeedPanel
            activeId={activeId}
            onSelect={runDig}
            source={source}
            onSource={setSource}
          />

          <div className="flex min-w-0 flex-col gap-3">
            {activeSeed ? (
              <SeedCard
                track={activeSeed}
                onVibe={() => {
                  const next = new URLSearchParams(params);
                  next.set("mode", "vibe");
                  if (activeSeed.key) next.set("camelot", activeSeed.key);
                  vibeDeepLinkKey.current = null;
                  setParams(next, { replace: true });
                }}
              />
            ) : (
              <div className="panel p-6">
                <p className="eyebrow">NO SEED SELECTED</p>
                <p className="mt-2 max-w-md text-sm text-ink-dim">
                  Pick a track in Dig Seeds — search for one, or hit DIG on any
                  row in the app. Every track you dig stays in the trail.
                </p>
              </div>
            )}

            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="eyebrow">SIMILAR MATCHES</p>
              <span className="font-mono text-[9px] uppercase tracking-[0.12em] text-ink-faint">
                digging from this track
              </span>
            </div>
            <form
              className="panel flex flex-wrap items-end gap-3 p-3"
              onSubmit={(e) => {
                e.preventDefault();
                setDigNonce((n) => n + 1);
              }}
            >
              <label className="filter-field font-mono text-[9px] uppercase tracking-[0.1em] text-ink-faint">
                LIMIT
                <input
                  type="number"
                  min={1}
                  max={200}
                  className="input !min-h-0 !h-10 !w-[76px] py-1.5 font-num text-xs"
                  value={limitInput}
                  onChange={(e) => setLimitInput(e.target.value)}
                  onBlur={() => setLimitInput(String(limit))}
                  aria-label="Result limit"
                />
              </label>
              <label className="filter-field font-mono text-[9px] uppercase tracking-[0.1em] text-ink-faint">
                BPM ±
                <input
                  type="number"
                  min={0}
                  max={30}
                  className="input !min-h-0 !h-10 !w-[76px] py-1.5 font-num text-xs"
                  value={bpmToleranceInput}
                  onChange={(e) => setBpmToleranceInput(e.target.value)}
                  onBlur={() => setBpmToleranceInput(String(bpmTolerance))}
                  aria-label="BPM tolerance"
                />
              </label>
              <label className="filter-field min-w-[120px] flex-1 font-mono text-[9px] uppercase tracking-[0.1em] text-ink-faint">
                GENRE
                <input
                  className="input !min-h-0 !h-10 py-1.5 text-xs"
                  placeholder="exact genre"
                  value={digGenre}
                  onChange={(e) => setDigGenre(e.target.value)}
                  aria-label="Genre filter"
                />
              </label>
              <label className="filter-field font-mono text-[9px] uppercase tracking-[0.1em] text-ink-faint">
                MIN YEAR
                <input
                  type="number"
                  min={1900}
                  max={2100}
                  className="input !min-h-0 !h-10 !w-[96px] py-1.5 font-num text-xs"
                  placeholder="any"
                  value={digMinYear}
                  onChange={(e) => setDigMinYear(e.target.value)}
                  aria-label="Minimum year"
                />
              </label>
              <label className="flex h-10 items-center gap-1.5 font-mono text-[10px] uppercase text-ink-dim">
                <input
                  type="checkbox"
                  className="h-4 w-4 accent-accent"
                  checked={harmonic}
                  onChange={(e) => setHarmonic(e.target.checked)}
                />
                HARMONIC
              </label>
              <label className="flex h-10 items-center gap-1.5 font-mono text-[10px] uppercase text-ink-dim">
                <input
                  type="checkbox"
                  className="h-4 w-4 accent-accent"
                  checked={excludeHeard}
                  onChange={(e) => setExcludeHeard(e.target.checked)}
                />
                HIDE HEARD
              </label>
              <button
                type="submit"
                className="btn btn-primary !min-h-0 h-10 font-mono text-[10px]"
                disabled={!activeSeed}
              >
                DIG &gt;
              </button>
            </form>

            {busy ? <Loading label="DIGGING…" /> : null}
            {digResult ? (
              digResult.matches.length === 0 ? (
                <EmptyState
                  title="NO MATCHES"
                  hint="Widen the BPM tolerance or turn off harmonic filtering."
                />
              ) : (
                <div className="panel overflow-hidden">
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
            ) : activeSeed && !busy ? (
              <EmptyState
                title="NO MATCHES YET"
                hint="This seed has no neighbours in the local index."
              />
            ) : null}
          </div>
        </section>
      ) : null}

      {mode === "foryou" ? (
        <section className="flex flex-col gap-3">
          <div
            className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-2"
            data-testid="taste-modes"
          >
            <div className="flex gap-4" role="tablist" aria-label="Taste mode">
              {TASTE_MODES.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  role="tab"
                  aria-selected={tasteMode === m.id}
                  onClick={() => setTasteMode(m.id)}
                  className="tab !min-h-11"
                >
                  {m.label}
                </button>
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {artistParam ? (
                <button
                  type="button"
                  onClick={() => {
                    const next = new URLSearchParams(params);
                    next.delete("artist");
                    setParams(next, { replace: true });
                  }}
                  className="pill pill-active min-h-9 gap-1.5 px-2.5 py-1 font-mono text-[10px]"
                  title="Clear artist seed filter"
                >
                  SEED ARTIST: {artistParam}
                  <X size={12} />
                </button>
              ) : null}
              {profile?.bpmMin != null || profile?.bpmMax != null ? (
                <span className="pill font-num">
                  {profile?.bpmMin ?? "—"}–{profile?.bpmMax ?? "—"} BPM
                </span>
              ) : null}
              <label className="flex min-h-11 items-center gap-2 rounded-pill border border-line bg-white/[0.03] px-3">
                <span className="eyebrow !text-[9px]">Profile</span>
                <select
                  aria-label="Taste profile"
                  className="h-9 rounded-pill border-0 bg-transparent pr-5 text-[12px] text-heading outline-none focus-visible:ring-2 focus-visible:ring-accent/70"
                  value={profile?.id ?? ""}
                  onChange={(event) => setActiveProfile(event.target.value)}
                >
                  {profiles.map((p) => (
                    <option key={p.id} value={p.id} className="bg-panel text-ink">
                      {p.name}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </div>
          {busy && !taste ? <Loading label="RANKING YOUR TASTE…" /> : null}
          {taste ? (
            taste.matches.length === 0 ? (
              <EmptyState
                title="NOTHING RANKED YET"
                hint={
                  artistParam
                    ? `No catalog tracks matched from ${artistParam}'s embedded tracks (or profile BPM/genre constraints).`
                    : "Taste ranking needs embedded local tracks (and liked artists for LIKED mode). Run the index job first."
                }
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
              if (vibeRangeError) return;
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
              <label className="filter-field font-mono text-[10px] uppercase tracking-[0.1em] text-ink-dim">
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
              <label className="filter-field font-mono text-[10px] uppercase tracking-[0.1em] text-ink-dim">
                BPM MIN
                <input
                  className="input !w-20 font-num"
                  type="number"
                  inputMode="numeric"
                  min={0}
                  max={200}
                  value={filterBpmMin}
                  onChange={(e) => setFilterBpmMin(e.target.value)}
                  aria-invalid={Boolean(vibeRangeError)}
                  aria-label="BPM minimum"
                />
              </label>
              <label className="filter-field font-mono text-[10px] uppercase tracking-[0.1em] text-ink-dim">
                BPM MAX
                <input
                  className="input !w-20 font-num"
                  type="number"
                  inputMode="numeric"
                  min={0}
                  max={200}
                  value={filterBpmMax}
                  onChange={(e) => setFilterBpmMax(e.target.value)}
                  aria-invalid={Boolean(vibeRangeError)}
                  aria-label="BPM maximum"
                />
              </label>
              <label className="filter-field min-w-[120px] flex-1 font-mono text-[10px] uppercase tracking-[0.1em] text-ink-dim">
                GENRE
                <input
                  className="input"
                  placeholder="exact genre"
                  value={filterGenre}
                  onChange={(e) => setFilterGenre(e.target.value)}
                  aria-label="Vibe genre filter"
                />
              </label>
              <label className="filter-field font-mono text-[10px] uppercase tracking-[0.1em] text-ink-dim">
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
                className="btn font-mono text-[10px]"
                onClick={() => {
                  setVibeQuery("");
                  setFilterKey("");
                  setFilterBpmMin("");
                  setFilterBpmMax("");
                  setFilterGenre("");
                  setFilterSource("");
                  setFilterResult(null);
                  setVibeResult(null);
                  setVibeRangeError(null);
                  setError(null);
                }}
              >
                RESET
              </button>
              {vibeRangeError ? (
                <p role="alert" className="font-mono text-[10px] uppercase tracking-[0.1em]" style={{ color: "var(--color-danger)" }}>
                  {vibeRangeError}
                </p>
              ) : (
                <p className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-faint">
                  Leave the vibe query empty to filter the catalog directly.
                </p>
              )}
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
