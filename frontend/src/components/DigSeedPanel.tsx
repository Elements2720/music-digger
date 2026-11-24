import { Search, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { Track } from "../types/apiTypes";
import { useDigTrailStore } from "../stores/digTrailStore";
import type { SeedSource } from "../stores/digTrailStore";
import { Artwork, KeyPill } from "./ui";

const SOURCES: { id: SeedSource; label: string }[] = [
  { id: "recent", label: "RECENT" },
  { id: "local", label: "LOCAL" },
  { id: "taste", label: "TASTE" },
];

function SeedThumb({
  track,
  active,
  onSelect,
  onRemove,
  chip = false,
}: {
  track: Track;
  active: boolean;
  onSelect: () => void;
  onRemove: () => void;
  chip?: boolean;
}) {
  return (
    <div
      className={`group relative flex items-center gap-2.5 rounded-[3px] border transition-colors ${
        chip ? "shrink-0 py-1 pl-1 pr-1.5" : "w-full p-1.5 text-left"
      } ${
        active
          ? "border-accent/60 bg-fill"
          : "border-transparent hover:bg-fill"
      }`}
      style={active ? { boxShadow: "inset 0 0 0 1px rgba(61,214,140,0.45)" } : undefined}
    >
      <button
        type="button"
        onClick={onSelect}
        className="flex min-w-0 flex-1 items-center gap-2.5 text-left"
        aria-current={active ? "true" : undefined}
        aria-label={`Dig from ${track.title} by ${track.artist}`}
      >
        <Artwork track={track} size={chip ? 28 : 40} className="!rounded-[3px]" />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13px] text-heading">
            {track.title}
          </span>
          {chip ? null : (
            <span className="block truncate text-[11px] text-ink-dim">
              {track.artist}
            </span>
          )}
          {chip ? null : (
            <span className="mt-1 flex items-center gap-1.5">
              <KeyPill k={track.key} className="!px-1.5 !py-0 !text-[9px]" />
              {track.has_local_file ? (
                <span
                  className="font-num text-[9px]"
                  style={{ color: "var(--color-ok)" }}
                >
                  LOCAL
                </span>
              ) : null}
            </span>
          )}
        </span>
        {chip ? (
          <KeyPill k={track.key} className="!px-1.5 !py-0 !text-[9px]" />
        ) : null}
      </button>
      <button
        type="button"
        onClick={onRemove}
        className="flex h-6 w-6 shrink-0 items-center justify-center rounded-[3px] text-ink-faint opacity-0 transition-opacity hover:bg-fill hover:text-heading focus-visible:opacity-100 group-hover:opacity-100"
        aria-label={`Remove ${track.title} from dig trail`}
      >
        <X size={12} />
      </button>
    </div>
  );
}

/** Left rail of the Match view: the session's dig trail plus seed sources. */
export function DigSeedPanel({
  activeId,
  onSelect,
  source,
  onSource,
}: {
  activeId: string | null;
  onSelect: (track: Track) => void;
  source: SeedSource;
  onSource: (source: SeedSource) => void;
}) {
  const seeds = useDigTrailStore((s) => s.seeds);
  const remove = useDigTrailStore((s) => s.remove);

  const [query, setQuery] = useState("");
  const [options, setOptions] = useState<Track[]>([]);
  const [searchState, setSearchState] = useState<
    "idle" | "ok" | "empty" | "error"
  >("idle");
  const [searchMessage, setSearchMessage] = useState<string | null>(null);

  const [loaded, setLoaded] = useState<Track[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

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
    const timer = window.setTimeout(() => void search(query), 250);
    return () => window.clearTimeout(timer);
  }, [query, search]);

  useEffect(() => {
    if (source === "recent") {
      setLoaded([]);
      setLoadError(null);
      setLoading(false);
      return;
    }
    let alive = true;
    setLoading(true);
    setLoadError(null);
    const request =
      source === "local"
        ? api
            .filterCatalog({ source: "local", limit: 40 })
            .then((res) => res.tracks)
        : api
            .tasteRanking({ mode: "both", limit: 20 })
            .then((res) => res.matches);
    request
      .then((tracks) => {
        if (alive) setLoaded(tracks);
      })
      .catch((err: unknown) => {
        if (alive && err instanceof Error) setLoadError(err.message);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [source, attempt]);

  const list = source === "recent" ? seeds : loaded;
  const emptyHint =
    source === "recent"
      ? "Search a track, or hit DIG on any row."
      : source === "local"
        ? "No local tracks yet — download or index first."
        : "No taste ranking yet — embed tracks first.";

  const pick = (track: Track) => {
    setQuery("");
    setOptions([]);
    setSearchState("idle");
    onSelect(track);
  };

  return (
    <aside
      aria-label="Dig seeds"
      className="panel p-3 lg:sticky lg:top-14 lg:max-h-[calc(100vh-96px)] lg:overflow-y-auto"
    >
      <div className="flex items-center justify-between">
        <p className="eyebrow">DIG SEEDS</p>
        <span className="font-num text-[10px] text-ink-faint">{list.length}</span>
      </div>

      <div className="relative mt-2">
        <Search
          size={14}
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint"
        />
        <input
          className="input !min-h-9 !pl-8 text-[12px]"
          placeholder="Add a seed track…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          autoComplete="off"
          aria-label="Add a seed track"
        />
      </div>
      {searchState === "error" ? (
        <p
          className="mt-1.5 font-mono text-[10px] uppercase tracking-[0.1em]"
          style={{ color: "var(--color-warn)" }}
          role="status"
        >
          SEARCH FAILED — {searchMessage ?? "try again"}
        </p>
      ) : searchState === "empty" ? (
        <p
          className="mt-1.5 font-mono text-[10px] uppercase tracking-[0.1em] text-ink-faint"
          role="status"
        >
          NO TRACKS FOUND
        </p>
      ) : null}
      {options.length > 0 ? (
        <ul className="mt-2 overflow-hidden rounded-[3px] border border-line">
          {options.map((t) => (
            <li key={t.id}>
              <button
                type="button"
                className="flex w-full items-center gap-2 px-2 py-1.5 text-left hover:bg-fill"
                onClick={() => pick(t)}
              >
                <Artwork track={t} size={28} className="!rounded-[3px]" />
                <span className="min-w-0">
                  <span className="block truncate text-[12px] text-heading">
                    {t.title}
                  </span>
                  <span className="block truncate text-[10px] text-ink-dim">
                    {t.artist}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      <div className="seg mt-2.5 w-full" role="tablist" aria-label="Seed source">
        {SOURCES.map((s) => (
          <button
            key={s.id}
            type="button"
            role="tab"
            aria-selected={source === s.id}
            onClick={() => onSource(s.id)}
            className="flex-1"
          >
            {s.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="mt-2 space-y-1.5" aria-hidden>
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-10 animate-pulse rounded-[3px] bg-white/5" />
          ))}
        </div>
      ) : loadError ? (
        <div className="mt-2 rounded-[3px] border border-line p-2">
          <p
            className="font-mono text-[10px] uppercase tracking-[0.1em]"
            style={{ color: "var(--color-warn)" }}
          >
            COULD NOT LOAD SEEDS
          </p>
          <button
            type="button"
            className="mt-1 font-mono text-[10px] uppercase tracking-[0.1em] text-accent"
            onClick={() => setAttempt((n) => n + 1)}
          >
            RETRY
          </button>
        </div>
      ) : list.length === 0 ? (
        <p className="mt-3 px-1 text-[11px] leading-relaxed text-ink-faint">
          {emptyHint}
        </p>
      ) : (
        <>
          {/* mobile: horizontal chip rail */}
          <div className="shelf no-scrollbar mt-2 lg:hidden">
            {list.map((t) => (
              <SeedThumb
                key={t.id}
                track={t}
                chip
                active={t.id === activeId}
                onSelect={() => onSelect(t)}
                onRemove={() => remove(t.id)}
              />
            ))}
          </div>
          {/* desktop: vertical list */}
          <ul className="mt-2 hidden space-y-0.5 lg:block">
            {list.map((t) => (
              <li key={t.id}>
                <SeedThumb
                  track={t}
                  active={t.id === activeId}
                  onSelect={() => onSelect(t)}
                  onRemove={() => remove(t.id)}
                />
              </li>
            ))}
          </ul>
        </>
      )}
    </aside>
  );
}
