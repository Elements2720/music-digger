import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  CheckSquare,
  Headphones,
  Heart,
  Plus,
  RotateCcw,
  Search,
  ShieldOff,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { api } from "../api/client";
import type {
  ArtistSummary,
  ArtistTracksResponse,
  BlacklistResponse,
  HardwareResponse,
  SeedsResponse,
  SimilarArtistsResponse,
} from "../types/apiTypes";
import {
  Artwork,
  ConfirmActionButton,
  EmptyState,
  ErrorState,
  Loading,
  PanelHead,
  TasteBadge,
  TasteBadgeCompact,
  TrackRow,
  useModalFocusTrap,
} from "../components/ui";
import { fmtCount, fmtPercent } from "../lib/format";
import { useCrateStore } from "../stores/crateStore";
import { useDigTrailStore } from "../stores/digTrailStore";
import { useLikesStore } from "../stores/likesStore";
import { usePlayerStore } from "../stores/playerStore";

type SubTab = "artists" | "cleanup" | "seeds" | "hardware";

// One shared desktop grid template for the Artists Hub header AND every row:
// identical string, fixed px data columns, only artist/genres flexible —
// so every column edge is shared and nothing re-solves per row.
const ARTIST_GRID =
  "lg:grid lg:grid-cols-[28px_minmax(160px,1.4fr)_56px_92px_84px_minmax(140px,1fr)_64px_80px_200px] lg:items-center lg:gap-x-3";

function ArtistModal({
  summary,
  onClose,
  onChanged,
}: {
  summary: ArtistSummary;
  onClose: () => void;
  onChanged?: () => void;
}) {
  const [data, setData] = useState<ArtistTracksResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [fetchState, setFetchState] = useState<"idle" | "busy" | "done" | "error">("idle");
  const [fetchMessage, setFetchMessage] = useState<string | null>(null);
  const modalRef = useRef<HTMLDivElement | null>(null);

  useModalFocusTrap(true, modalRef, onClose);

  const loadTracks = useCallback(() => {
    setError(null);
    api
      .artistTracks(summary.artist)
      .then(setData)
      .catch((err: unknown) => err instanceof Error && setError(err.message));
  }, [summary.artist]);

  useEffect(() => {
    loadTracks();
  }, [loadTracks]);

  const heardIds = useLikesStore((s) => s.heardIds);
  const bulkHeard = useLikesStore((s) => s.bulkHeard);
  const tracks = data?.tracks ?? [];
  const needle = filter.trim().toLowerCase();
  const visible = needle
    ? tracks.filter(
        (t) =>
          t.title.toLowerCase().includes(needle) || t.artist.toLowerCase().includes(needle),
      )
    : tracks;
  const allHeard =
    tracks.length > 0 && tracks.every((track) => heardIds.has(track.id));

  const fetchMore = async () => {
    setFetchState("busy");
    setFetchMessage(null);
    try {
      await api.startJob("fetch-artist", {
        artist: summary.artist,
        tracks_per_artist: 50,
        auto_index: true,
        discover_related: false,
        related_limit: 10,
        min_year: summary.year_min ?? undefined,
      });
      setFetchState("done");
      setFetchMessage(`Fetch started for ${summary.artist} — follow it in Pipeline.`);
    } catch (err) {
      setFetchState("error");
      setFetchMessage(err instanceof Error ? err.message : "Could not start fetch");
    }
  };

  const removeTrack = async (trackId: string) => {
    try {
      await api.deleteTrack(trackId);
      useCrateStore.getState().remove(trackId);
      usePlayerStore.getState().removeTrack(trackId);
      useDigTrailStore.getState().remove(trackId);
      useLikesStore.getState().removeTrack(trackId);
      setData((prev) =>
        prev ? { ...prev, tracks: prev.tracks.filter((t) => t.id !== trackId) } : prev,
      );
      onChanged?.();
    } catch (err) {
      if (err instanceof Error) setError(err.message);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4">
      <div className="absolute inset-0 bg-black/70" onClick={onClose} aria-hidden />
      <div
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        tabIndex={-1}
        aria-label={`Artist ${summary.artist}`}
        className="panel relative flex max-h-[88vh] w-full max-w-3xl flex-col focus:outline-none"
      >
        <div className="panel-head flex-wrap gap-2">
          <span className="min-w-0 flex-1">
            <span className="flex min-w-0 items-baseline gap-2">
              <span className="truncate text-sm font-semibold text-heading">
                {summary.artist}
              </span>
              <span className="font-num shrink-0 text-[11px] text-ink-faint">
                {fmtCount(tracks.length)} tracks
              </span>
            </span>
            <span className="font-num block truncate text-[11px] text-ink-dim">
              {summary.embedded_count} embedded (
              {fmtPercent(
                summary.track_count > 0
                  ? (summary.embedded_count / summary.track_count) * 100
                  : 0,
              )}
              ){summary.taste_match_percent != null
                ? ` · ${fmtPercent(summary.taste_match_percent)} taste`
                : " · no taste score"}
            </span>
          </span>
          <button
            type="button"
            className={`flex h-9 min-h-0 items-center gap-1.5 rounded-pill border px-3 text-[10px] transition-colors ${
              allHeard
                ? "border-accent/60 bg-accent/15 text-accent"
                : "border-line text-ink-dim hover:border-white/25 hover:text-heading"
            }`}
            aria-pressed={allHeard}
            aria-label={
              allHeard
                ? `Unmark all ${summary.artist} tracks as heard`
                : `Mark all ${summary.artist} tracks as heard`
            }
            onClick={() => void bulkHeard(tracks.map((t) => t.id), !allHeard)}
            title={
              allHeard ? "Unmark all tracks as heard" : "Mark all tracks as heard"
            }
          >
            <Headphones size={13} />
            {allHeard ? "All heard" : "Mark all heard"}
          </button>
          <button
            type="button"
            className="btn btn-accent !min-h-0 gap-1 px-2.5 py-2 font-mono text-[10px]"
            onClick={() => void fetchMore()}
            disabled={fetchState === "busy"}
          >
            <Plus size={12} /> {fetchState === "busy" ? "FETCHING…" : "+ FETCH MORE"}
          </button>
          <Link
            to={`/dig?mode=foryou&artist=${encodeURIComponent(summary.artist)}`}
            className="btn btn-ghost !min-h-0 px-2 py-2 font-mono text-[10px]"
            title="Dig this artist's taste"
            onClick={onClose}
          >
            DIG
          </Link>
          <button
            type="button"
            className="btn btn-ghost !min-h-0 p-2"
            onClick={onClose}
            aria-label="Close artist details"
          >
            <X size={16} />
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
          <div className="input-icon-wrap min-w-0 flex-1">
            <Search
              size={13}
              aria-hidden
            />
            <input
              className="input !min-h-0 py-2 text-xs"
              placeholder="Filter tracks…"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              aria-label="Filter artist tracks"
            />
          </div>
          <span className="font-num text-[10px] text-ink-faint">
            {visible.length} / {tracks.length}
          </span>
        </div>
        {fetchMessage ? (
          <p
            className="border-b border-line px-3 py-2 text-[11px]"
            style={{ color: fetchState === "error" ? "var(--color-danger)" : "var(--color-accent)" }}
            role="status"
          >
            {fetchMessage}
          </p>
        ) : null}
        <div className="scroll-thin min-h-0 flex-1 overflow-y-auto">
          {error ? <ErrorState message={error} onRetry={loadTracks} /> : null}
          {!data && !error ? <Loading /> : null}
          {data && visible.length === 0 ? (
            <p className="p-4 text-sm text-ink-dim">No tracks match that filter.</p>
          ) : null}
          {visible.map((t) => (
            <TrackRow
              key={t.id}
              track={t}
              queue={visible}
              trailing={
                <ConfirmActionButton
                  onConfirm={() => removeTrack(t.id)}
                  label={<X size={15} />}
                  confirmLabel="DEL?"
                  className="btn btn-ghost !min-h-0 !border-0 !bg-transparent p-1.5 text-danger hover:!bg-fill"
                  ariaLabel={`Delete ${t.title}`}
                  confirmAriaLabel={`Confirm deleting ${t.title}`}
                  title="Delete this track"
                />
              }
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function ArtistsHub({ onOpenCleanup }: { onOpenCleanup: () => void }) {
  const [q, setQ] = useState("");
  const [likedOnly, setLikedOnly] = useState(false);
  const [data, setData] = useState<ArtistSummary[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<ArtistSummary | null>(null);
  const [genre, setGenre] = useState("");
  const [genres, setGenres] = useState<string[]>([]);
  const [source, setSource] = useState("");
  const [minYear, setMinYear] = useState("");
  const [sort, setSort] = useState("tracks");
  const [tasteMode, setTasteMode] = useState("both");
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [similar, setSimilar] = useState<SimilarArtistsResponse | null>(null);
  const [similarOpen, setSimilarOpen] = useState(false);
  const [fetchOpen, setFetchOpen] = useState(false);
  const [fetchName, setFetchName] = useState("");
  const [fetchBusy, setFetchBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .artists({
        q: q || undefined,
        liked_only: likedOnly || undefined,
        genre: genre || undefined,
        source: source || undefined,
        min_year: minYear ? Number(minYear) : undefined,
        sort,
        taste_mode: tasteMode,
        limit: 200,
      })
      .then((res) => {
        setData(res.artists);
        setTotal(res.total);
        setError(null);
      })
      .catch((err: unknown) => err instanceof Error && setError(err.message));
  }, [q, likedOnly, genre, source, minYear, sort, tasteMode]);

  useEffect(() => {
    const t = window.setTimeout(load, 250);
    return () => window.clearTimeout(t);
  }, [load]);

  useEffect(() => {
    api
      .analytics()
      .then((res) => setGenres((res.genres ?? []).map((g) => g.genre)))
      .catch(() => undefined);
  }, []);

  const loadSimilar = useCallback(() => {
    setSimilar(null);
    api
      .similarArtists({ limit: 24 })
      .then(setSimilar)
      .catch((err: unknown) => err instanceof Error && setError(err.message));
  }, []);

  useEffect(() => {
    if (similarOpen) loadSimilar();
  }, [similarOpen, loadSimilar]);

  const startFetch = async (artist: string) => {
    const clean = artist.trim();
    if (!clean) return;
    setFetchBusy(true);
    setStatus(null);
    try {
      await api.startJob("fetch-artist", {
        artist: clean,
        tracks_per_artist: 50,
        auto_index: true,
        discover_related: false,
        related_limit: 10,
        min_year: minYear ? Number(minYear) : undefined,
        electronic_only: false,
      });
      setStatus(`Fetch started for “${clean}” — follow it in Pipeline.`);
      setFetchName("");
      setFetchOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start fetch");
    } finally {
      setFetchBusy(false);
    }
  };

  const toggleLike = async (a: { artist: string; is_liked: boolean }) => {
    try {
      if (a.is_liked) await api.unlikeArtist(a.artist);
      else await api.likeArtist(a.artist);
      load();
      if (similarOpen) loadSimilar();
    } catch (err) {
      if (err instanceof Error) setError(err.message);
    }
  };

  const toggleChecked = (name: string) => {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const bulkDelete = async () => {
    if (checked.size === 0) return;
    try {
      const targetNames = [...checked];
      const res = await api.bulkDeleteArtists({
        artist_names: targetNames,
        blacklist: true,
        reason: "manual bulk delete",
      });
      setChecked(new Set());
      setError(null);
      load();
      setSimilar(null);
      setStatus(
        `Deleted ${res.artists_deleted} artists / ${res.tracks_deleted} tracks · ${res.blacklisted_count} blacklisted`,
      );
    } catch (err) {
      if (err instanceof Error) setError(err.message);
    }
  };

  const deleteArtist = async (a: { artist: string }) => {
    try {
      await api.deleteArtist(a.artist, true, "manual delete");
      setSelected(null);
      load();
      if (similarOpen) loadSimilar();
      setStatus(`Deleted "${a.artist}" and added to blacklist.`);
    } catch (err) {
      if (err instanceof Error) setError(err.message);
    }
  };

  const toggleSimilar = () => {
    setSimilarOpen((v) => !v);
  };

  const allChecked = !!data && data.length > 0 && checked.size === data.length;

  return (
    <div className="flex flex-col gap-3">
      <form
        className="panel flex flex-col gap-2 p-3"
        onSubmit={(e) => {
          e.preventDefault();
          load();
        }}
      >
        <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
          <div className="input-icon-wrap col-span-2 min-w-[160px] sm:flex-1">
            <Search size={14} aria-hidden />
            <input
              className="input"
              placeholder="Search artists…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              aria-label="Filter artists"
            />
          </div>
          <select
            className="input w-full sm:!w-auto sm:max-w-[150px]"
            value={source}
            onChange={(e) => setSource(e.target.value)}
            aria-label="Source filter"
          >
            <option value="">ALL SOURCES</option>
            <option value="deezer">DEEZER</option>
            <option value="itunes">ITUNES</option>
            <option value="local">LOCAL</option>
          </select>
          <select
            className="input w-full sm:!w-auto sm:max-w-[170px]"
            value={genre}
            onChange={(e) => setGenre(e.target.value)}
            aria-label="Genre filter"
          >
            <option value="">ALL GENRES</option>
            {genres.map((g) => (
              <option key={g} value={g}>
                {g.toUpperCase()}
              </option>
            ))}
          </select>
          <input
            className="input w-full sm:!w-[112px]"
            type="number"
            inputMode="numeric"
            placeholder="Min Year"
            value={minYear}
            onChange={(e) => setMinYear(e.target.value)}
            aria-label="Minimum release year"
          />
          <select
            className="input w-full sm:!w-auto sm:max-w-[170px]"
            value={sort}
            onChange={(e) => setSort(e.target.value)}
            aria-label="Sort artists"
          >
            <option value="tracks">MOST TRACKS</option>
            <option value="taste">TASTE</option>
            <option value="name">NAME A–Z</option>
          </select>
          <select
            className="input col-span-2 w-full sm:col-span-1 sm:!w-auto sm:max-w-[180px]"
            value={tasteMode}
            onChange={(e) => setTasteMode(e.target.value)}
            aria-label="Taste mode"
          >
            <option value="both">TASTE: AUTO (BOTH)</option>
            <option value="local">TASTE: LOCAL</option>
            <option value="liked">TASTE: LIKED</option>
          </select>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            className="btn btn-ghost min-h-10 px-2.5 py-1.5 font-mono text-[10px] sm:!min-h-0"
            aria-pressed={likedOnly}
            onClick={() => setLikedOnly((v) => !v)}
            style={
              likedOnly
                ? { borderColor: "var(--color-accent)", color: "var(--color-accent)" }
                : undefined
            }
          >
            <Heart size={12} fill={likedOnly ? "currentColor" : "none"} /> LIKED ONLY
          </button>
          <button
            type="button"
            className="btn btn-ghost min-h-10 px-2.5 py-1.5 font-mono text-[10px] sm:!min-h-0"
            aria-pressed={similarOpen}
            onClick={toggleSimilar}
            style={
              similarOpen
                ? { borderColor: "var(--color-accent)", color: "var(--color-accent)" }
                : undefined
            }
          >
            <Sparkles size={12} /> SIMILAR TO LIKED
          </button>
          <button
            type="button"
            className="btn btn-accent min-h-10 gap-1 px-2.5 py-1.5 font-mono text-[10px] sm:!min-h-0"
            aria-expanded={fetchOpen}
            onClick={() => setFetchOpen((v) => !v)}
          >
            <Plus size={12} /> FETCH ARTIST
          </button>
          <button
            type="button"
            className="btn btn-ghost min-h-10 gap-1 px-2.5 py-1.5 font-mono text-[10px] sm:!min-h-0"
            onClick={onOpenCleanup}
          >
            <RotateCcw size={12} /> BULK CLEANUP
          </button>
          <span className="font-num ml-auto text-[10px] text-ink-faint">
            {fmtCount(total)} artists in scope
          </span>
        </div>
        {fetchOpen ? (
          <div className="flex flex-wrap items-center gap-2 rounded-sm border border-line bg-panel-2/60 p-2">
            <input
              className="input min-w-[160px] flex-1"
              placeholder="Artist name to fetch…"
              value={fetchName}
              onChange={(e) => setFetchName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  void startFetch(fetchName || q);
                }
              }}
              aria-label="Artist to fetch"
            />
            <button
              type="button"
              className="btn btn-accent !min-h-0 px-3 py-1.5 font-mono text-[10px]"
              disabled={fetchBusy || !(fetchName || q).trim()}
              onClick={() => void startFetch(fetchName || q)}
            >
              {fetchBusy ? "STARTING…" : "FETCH"}
            </button>
            <span className="font-mono text-[9px] uppercase tracking-[0.12em] text-ink-faint">
              50 tracks · auto-index
            </span>
          </div>
        ) : null}
        {status ? (
          <p className="text-[11px] text-accent" role="status">
            {status}
          </p>
        ) : null}
      </form>

      {similarOpen ? (
        <section className="panel" aria-label="Similar to liked artists">
          <PanelHead
            title="SIMILAR TO LIKED"
            right={
              <button
                type="button"
                className="btn btn-ghost !min-h-0 px-2 py-1 font-mono text-[10px]"
                onClick={loadSimilar}
              >
                REFRESH
              </button>
            }
          />
          {!similar ? (
            <Loading label="FINDING NEIGHBOURS…" />
          ) : similar.items.length === 0 ? (
            <p className="p-4 text-sm text-ink-dim">
              Like a few artists first — this view suggests neighbours from your taste
              profile.
            </p>
          ) : (
            <ul className="divide-y divide-line">
              {similar.items.map((a) => (
                <li
                  key={a.artist}
                  className="flex flex-wrap items-center gap-2 px-3 py-2 sm:gap-3"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block break-words text-sm text-heading">
                      {a.artist}
                    </span>
                    <span className="font-num mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px] text-ink-dim">
                      {fmtPercent(a.similarity_percent)} match
                      <span className="text-ink-faint">·</span>
                      {a.track_count} tracks · {a.embedded_count} embedded
                      {a.year_min != null ? (
                        <>
                          <span className="text-ink-faint">·</span>
                          {a.year_min}–{a.year_max ?? a.year_min}
                        </>
                      ) : null}
                    </span>
                  </span>
                  <span className="hidden gap-1 md:flex">
                    {a.genres.slice(0, 2).map((g) => (
                      <span key={g} className="pill font-num uppercase text-ink-dim">
                        {g}
                      </span>
                    ))}
                  </span>
                  <div className="flex shrink-0 items-center gap-1">
                    <button
                      type="button"
                      className="btn btn-accent !min-h-0 px-2 py-1.5 font-mono text-[9px]"
                      onClick={() => void startFetch(a.artist)}
                    >
                      FETCH
                    </button>
                    <Link
                      to={`/dig?mode=foryou&artist=${encodeURIComponent(a.artist)}`}
                      className="btn btn-ghost !min-h-0 px-2 py-1.5 font-mono text-[9px]"
                    >
                      DIG
                    </Link>
                    <button
                      type="button"
                      className="btn btn-ghost !min-h-0 p-1.5"
                      onClick={() => void toggleLike(a)}
                      aria-label={`Like ${a.artist}`}
                      aria-pressed={a.is_liked}
                    >
                      <Heart
                        size={14}
                        className={a.is_liked ? "heart-on" : "text-ink-faint"}
                        fill={a.is_liked ? "currentColor" : "none"}
                      />
                    </button>
                    <ConfirmActionButton
                      onConfirm={() => deleteArtist(a)}
                      label={<Trash2 size={14} />}
                      confirmLabel="DEL?"
                      className="btn btn-ghost !min-h-0 p-1.5 text-danger"
                      ariaLabel={`Delete ${a.artist}`}
                      confirmAriaLabel={`Confirm deleting ${a.artist}`}
                    />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : null}

      {error ? <ErrorState message={error} onRetry={load} /> : null}
      {!data ? (
        <Loading label="LOADING ARTISTS…" />
      ) : data.length === 0 ? (
        <EmptyState title="NO ARTISTS" hint="Index or download some tracks first." />
      ) : (
        <div className="panel" data-testid="artist-list">
        <div className="scroll-thin min-w-0 overflow-x-auto">
          <div className="min-w-0 lg:min-w-[1040px]">
          <div className={`flex flex-wrap items-center gap-2 border-b border-line px-3 py-2 ${ARTIST_GRID}`}>
            <input
              type="checkbox"
              className="h-4 w-4 shrink-0 accent-accent"
              checked={allChecked}
              onChange={() =>
                setChecked(allChecked ? new Set() : new Set(data.map((a) => a.artist)))
              }
              aria-label="Select all artists"
            />
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              <span className="eyebrow">{fmtCount(total)} ARTISTS</span>
              <button
                type="button"
                className="btn btn-ghost !min-h-0 py-1 font-mono text-[10px]"
                onClick={() =>
                  setChecked(allChecked ? new Set() : new Set(data.map((a) => a.artist)))
                }
              >
                <CheckSquare size={13} /> {allChecked ? "CLEAR" : "SELECT ALL"}
              </button>
              {checked.size > 0 ? (
                <ConfirmActionButton
                  onConfirm={bulkDelete}
                  label={
                    <>
                      <Trash2 size={13} /> DELETE {checked.size} + BLACKLIST
                    </>
                  }
                  confirmLabel={`CONFIRM DELETE ${checked.size}?`}
                  className="btn btn-danger !min-h-0 py-1 font-mono text-[10px]"
                />
              ) : null}
            </div>
            <span className="hidden font-mono text-[8px] uppercase tracking-[0.12em] text-ink-faint lg:block">
              Tracks
            </span>
            <span className="hidden font-mono text-[8px] uppercase tracking-[0.12em] text-ink-faint lg:block">
              Embedded
            </span>
            <span className="hidden font-mono text-[8px] uppercase tracking-[0.12em] text-ink-faint lg:block">
              Years
            </span>
            <span className="hidden font-mono text-[8px] uppercase tracking-[0.12em] text-ink-faint lg:block">
              Genres
            </span>
            <span className="hidden font-mono text-[8px] uppercase tracking-[0.12em] text-ink-faint lg:block">
              Taste
            </span>
            <span className="hidden font-mono text-[8px] uppercase tracking-[0.12em] text-ink-faint lg:block">
              Sources
            </span>
            <span className="hidden font-mono text-[8px] uppercase tracking-[0.12em] text-ink-faint lg:block">
              Actions
            </span>
          </div>
          {data.map((a) => {
            const embeddedPct =
              a.track_count > 0 ? (a.embedded_count / a.track_count) * 100 : 0;
            return (
              <div
                key={a.artist}
                className={`flex flex-wrap items-center gap-2 border-b border-line px-3 py-2 last:border-b-0 hover:bg-panel-2/60 sm:gap-3 ${ARTIST_GRID} lg:py-1`}
              >
                <input
                  type="checkbox"
                  className="h-4 w-4 shrink-0 accent-accent"
                  checked={checked.has(a.artist)}
                  onChange={() => toggleChecked(a.artist)}
                  aria-label={`Select ${a.artist}`}
                />
                <button
                  type="button"
                  className="flex min-w-0 flex-1 items-center gap-3 text-left"
                  onClick={() => setSelected(a)}
                  aria-label={`Open ${a.artist}`}
                >
                  <Artwork
                    track={{
                      id: a.sample_track_id,
                      title: a.sample_track_title,
                      artist: a.artist,
                      artwork_url: a.artwork_url,
                    }}
                    size={40}
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm text-heading">{a.artist}</span>
                    <span className="font-num block text-[11px] text-ink-dim lg:hidden">
                      {fmtCount(a.track_count)} tracks · {fmtCount(a.embedded_count)} (
                      {fmtPercent(embeddedPct)}) embedded
                      {a.year_min != null
                        ? ` · ${a.year_min}–${a.year_max ?? a.year_min}`
                        : ""}
                    </span>
                    <span className="mt-1 flex flex-wrap items-center gap-1 lg:hidden">
                      {a.genres.slice(0, 2).map((g) => (
                        <span key={g} className="pill font-num uppercase text-ink-dim">
                          {g}
                        </span>
                      ))}
                      {a.sources.slice(0, 1).map((s) => (
                        <span key={s} className="pill font-num uppercase text-ink-faint">
                          {s}
                        </span>
                      ))}
                      {a.taste_match_percent != null ? (
                        <TasteBadge percent={a.taste_match_percent} />
                      ) : null}
                    </span>
                  </span>
                </button>
                <div className="hidden lg:contents">
                  <span className="font-num text-[12px] text-heading">
                    {fmtCount(a.track_count)}
                  </span>
                  <span className="font-num whitespace-nowrap text-[11px] text-ink-dim">
                    {fmtCount(a.embedded_count)} ({fmtPercent(embeddedPct)})
                  </span>
                  <span className="font-num text-[11px] text-ink-dim">
                    {a.year_min != null ? `${a.year_min}–${a.year_max ?? a.year_min}` : "—"}
                  </span>
                  <span className="flex min-w-0 items-center gap-1 overflow-hidden">
                    {a.genres.slice(0, 2).map((g) => (
                      <span
                        key={g}
                        className="pill max-w-[74px] truncate font-num uppercase text-ink-dim"
                      >
                        {g}
                      </span>
                    ))}
                    {a.genres.length > 2 ? (
                      <span className="font-num text-[9px] text-ink-faint">
                        +{a.genres.length - 2}
                      </span>
                    ) : null}
                  </span>
                  <span className="flex overflow-hidden">
                    {a.taste_match_percent != null ? (
                      <TasteBadgeCompact percent={a.taste_match_percent} className="w-16 justify-center" />
                    ) : (
                      <span className="font-num w-16 text-[10px] text-ink-faint">—</span>
                    )}
                  </span>
                  <span className="flex gap-1 overflow-hidden">
                    {a.sources.slice(0, 1).map((s) => (
                      <span
                        key={s}
                        className="pill max-w-[70px] truncate font-num uppercase text-ink-faint"
                      >
                        {s}
                      </span>
                    ))}
                  </span>
                </div>
                <div className="flex w-full shrink-0 flex-wrap items-center justify-end gap-1 lg:w-auto lg:flex-nowrap lg:justify-start">
                  <button
                    type="button"
                    className="btn btn-accent !min-h-0 px-2 py-1.5 font-mono text-[9px]"
                    onClick={() => void startFetch(a.artist)}
                    title={`Fetch more tracks for ${a.artist}`}
                  >
                    FETCH
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost !min-h-0 px-2 py-1.5 font-mono text-[9px]"
                    onClick={() => setSelected(a)}
                  >
                    TRACKS
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost !min-h-0 p-1.5"
                    onClick={() => void toggleLike(a)}
                    aria-label={a.is_liked ? `Unlike ${a.artist}` : `Like ${a.artist}`}
                    aria-pressed={a.is_liked}
                  >
                    <Heart
                      size={14}
                      className={a.is_liked ? "heart-on" : "text-ink-faint"}
                      fill={a.is_liked ? "currentColor" : "none"}
                    />
                  </button>
                  <ConfirmActionButton
                    onConfirm={() => deleteArtist(a)}
                    label={<Trash2 size={14} />}
                    confirmLabel="DEL?"
                    className="btn btn-ghost !min-h-0 p-1.5 text-danger"
                    ariaLabel={`Delete ${a.artist}`}
                    confirmAriaLabel={`Confirm deleting ${a.artist}`}
                    title="Delete artist and blacklist"
                  />
                  <Link
                    to={`/dig?mode=foryou&artist=${encodeURIComponent(a.artist)}`}
                    className="btn btn-ghost !min-h-0 px-2 py-1.5 font-mono text-[9px]"
                    title="Dig tracks by this artist and similar taste"
                  >
                    DIG
                  </Link>
                </div>
              </div>
            );
          })}
          </div>
        </div>
        </div>
      )}
      {selected ? (
        <ArtistModal
          summary={selected}
          onClose={() => setSelected(null)}
          onChanged={load}
        />
      ) : null}
    </div>
  );
}

function CleanupWizard() {
  const [maxTaste, setMaxTaste] = useState(40);
  const [protectLiked, setProtectLiked] = useState(true);
  const [protectLocal, setProtectLocal] = useState(true);
  const [preview, setPreview] = useState<{
    artist_count: number;
    track_count: number;
    skipped_count: number;
    sample_artists: ArtistSummary[];
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [busyLabel, setBusyLabel] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const runPreview = async () => {
    setBusy(true);
    setBusyLabel("SCANNING…");
    setError(null);
    try {
      setPreview(
        await api.bulkCleanupPreview({
          max_taste_percent: maxTaste,
          protect_liked: protectLiked,
          protect_local: protectLocal,
        }),
      );
    } catch (err) {
      if (err instanceof Error) setError(err.message);
    } finally {
      setBusy(false);
      setBusyLabel(null);
    }
  };

  const execute = async () => {
    if (!preview || preview.artist_count === 0) return;
    if (!window.confirm(`Delete ${preview.artist_count} artists (${preview.track_count} tracks)?`))
      return;
    setBusy(true);
    setBusyLabel("DELETING…");
    try {
      const res = await api.bulkCleanupExecute({
        max_taste_percent: maxTaste,
        protect_liked: protectLiked,
        protect_local: protectLocal,
        blacklist: true,
        reason: "bulk cleanup",
      });
      setStatus(
        `Deleted ${res.artists_deleted} artists / ${res.tracks_deleted} tracks · ${res.blacklisted_count} blacklisted`,
      );
      setPreview(null);
    } catch (err) {
      if (err instanceof Error) setError(err.message);
    } finally {
      setBusy(false);
      setBusyLabel(null);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="panel p-4">
        <p className="eyebrow mb-3">RULE-BASED CLEANUP — DELETE WEAK-TASTE ARTISTS</p>
        <label className="mb-3 block font-mono text-[11px] uppercase tracking-[0.1em] text-ink-dim">
          MAX TASTE MATCH: <span className="font-num text-heading">{maxTaste}%</span>
          <input
            type="range"
            min={0}
            max={100}
            value={maxTaste}
            onChange={(e) => setMaxTaste(Number(e.target.value))}
            className="mt-2 h-6 w-full cursor-pointer accent-accent"
            aria-label="Maximum taste percent"
          />
        </label>
        <div className="flex flex-wrap gap-4">
          <label className="flex items-center gap-2 font-mono text-[11px] uppercase text-ink-dim">
            <input
              type="checkbox"
              checked={protectLiked}
              onChange={(e) => setProtectLiked(e.target.checked)}
              className="h-4 w-4 accent-accent"
            />
            PROTECT LIKED
          </label>
          <label className="flex items-center gap-2 font-mono text-[11px] uppercase text-ink-dim">
            <input
              type="checkbox"
              checked={protectLocal}
              onChange={(e) => setProtectLocal(e.target.checked)}
              className="h-4 w-4 accent-accent"
            />
            PROTECT LOCAL FILES
          </label>
          <button
            type="button"
            className="btn ml-auto"
            onClick={() => void runPreview()}
            disabled={busy}
          >
            {busy && busyLabel ? busyLabel : "PREVIEW"}
          </button>
        </div>
      </div>

      {error ? <ErrorState message={error} /> : null}
      {status ? (
        <p className="font-mono text-xs text-accent" role="status">
          {status}
        </p>
      ) : null}

      {preview ? (
        <div className="panel">
          <PanelHead
            title={`${preview.artist_count} ARTISTS / ${preview.track_count} TRACKS SELECTED`}
            right={
              <button
                type="button"
                className="btn btn-danger !min-h-0 py-1.5"
                onClick={() => void execute()}
                disabled={busy || preview.artist_count === 0}
              >
                <Trash2 size={13} /> DELETE ALL
              </button>
            }
          />
          {preview.skipped_count > 0 ? (
            <p className="border-b border-line px-3 py-2 font-mono text-[11px] uppercase text-ink-dim" role="status">
              {preview.skipped_count} in-scope artists skipped (taste match above {maxTaste}% or not scored yet)
            </p>
          ) : null}
          {preview.artist_count === 0 ? (
            <p className="px-3 py-3 font-mono text-xs text-ink-dim" role="status">
              No artists matched. Lower the taste threshold or check that your taste profile has
              liked seeds.
            </p>
          ) : (
            <ul className="divide-y divide-line">
              {preview.sample_artists.map((a) => (
                <li key={a.artist} className="flex items-center gap-3 px-3 py-2">
                  <span className="min-w-0 flex-1 truncate text-sm text-heading">{a.artist}</span>
                  <span className="font-num text-xs text-ink-dim">{a.track_count} tracks</span>
                  <span className="font-num text-xs text-ink-faint">
                    {fmtPercent(a.taste_match_percent)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  );
}

function SeedsBlacklist() {
  const [seeds, setSeeds] = useState<SeedsResponse | null>(null);
  const [blacklist, setBlacklist] = useState<BlacklistResponse | null>(null);
  const [name, setName] = useState("");
  const [kind, setKind] = useState<"artist" | "track">("artist");
  const [bq, setBq] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .seeds({ limit: 100 })
      .then(setSeeds)
      .catch((err: unknown) => err instanceof Error && setError(err.message));
    api
      .blacklist({ q: bq || undefined, limit: 100 })
      .then(setBlacklist)
      .catch(() => undefined);
  }, [bq]);

  useEffect(load, [load]);

  const addBlacklist = async () => {
    if (!name.trim()) return;
    try {
      await api.addBlacklist({ kind, name: name.trim(), reason: "manual" });
      setName("");
      load();
    } catch (err) {
      if (err instanceof Error) setError(err.message);
    }
  };

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      {error ? (
        <div className="lg:col-span-2">
          <ErrorState
            message={error}
            onRetry={() => {
              setError(null);
              load();
            }}
          />
        </div>
      ) : null}

      <section className="panel self-start">
        <PanelHead
          title={`CATALOG SEEDS${seeds ? ` — ${fmtCount(seeds.total)}` : ""}`}
          right={
            <span className="flex flex-wrap gap-1">
              <ConfirmActionButton
                onConfirm={() => api.purgeSeeds({ status: "failed" }).then(load).catch((e) => setError(e instanceof Error ? e.message : "Purge failed"))}
                label="PURGE FAILED"
                confirmLabel="CONFIRM?"
                className="btn btn-ghost !min-h-0 py-1 font-mono text-[10px]"
              />
              <ConfirmActionButton
                onConfirm={() => api.purgeSeeds({ category: "general" }).then(load).catch((e) => setError(e instanceof Error ? e.message : "Purge failed"))}
                label="PURGE GENERAL"
                confirmLabel="CONFIRM?"
                className="btn btn-ghost !min-h-0 py-1 font-mono text-[10px]"
              />
              <ConfirmActionButton
                onConfirm={() => api.purgeSeeds({ status: "pending" }).then(load).catch((e) => setError(e instanceof Error ? e.message : "Purge failed"))}
                label="PURGE PENDING"
                confirmLabel="CONFIRM?"
                className="btn btn-danger !min-h-0 py-1 font-mono text-[10px]"
              />
            </span>
          }
        />
        {!seeds ? (
          <Loading />
        ) : seeds.seeds.length === 0 ? (
          <p className="p-4 text-sm text-ink-dim">No seeds yet — run seed-crawl.</p>
        ) : (
          <ul className="scroll-thin max-h-[420px] divide-y divide-line overflow-y-auto">
            {seeds.seeds.map((s) => (
              <li key={s.name} className="flex items-center gap-2 px-3 py-2">
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm text-heading">{s.name}</span>
                  <span className="font-num block text-[11px] uppercase text-ink-dim">
                    {s.category} · {s.status}
                    {s.source ? ` · ${s.source}` : ""}
                  </span>
                </span>
                <ConfirmActionButton
                  onConfirm={() => api.deleteSeed(s.name).then(load).catch((e) => setError(e instanceof Error ? e.message : "Delete failed"))}
                  label={<Trash2 size={14} />}
                  confirmLabel="DEL?"
                  className="btn btn-ghost !min-h-0 p-2 text-danger"
                  ariaLabel={`Delete seed ${s.name}`}
                  confirmAriaLabel={`Confirm deleting seed ${s.name}`}
                />
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel self-start">
        <PanelHead title="BLACKLIST" />
        <form
          className="flex flex-wrap gap-2 p-3"
          onSubmit={(e) => {
            e.preventDefault();
            void addBlacklist();
          }}
        >
          <select
            className="input !w-auto"
            value={kind}
            onChange={(e) => setKind(e.target.value as "artist" | "track")}
            aria-label="Block kind"
          >
            <option value="artist">ARTIST</option>
            <option value="track">TRACK</option>
          </select>
          <input
            className="input min-w-[160px] flex-1"
            placeholder="Artist name to block…"
            value={name}
            onChange={(e) => setName(e.target.value)}
            aria-label="Artist name to block"
          />
          <button type="submit" className="btn">
            <Plus size={14} /> BLOCK
          </button>
        </form>
        <div className="px-3 pb-2">
          <input
            className="input"
            placeholder="Filter blocked names…"
            value={bq}
            onChange={(e) => setBq(e.target.value)}
            aria-label="Filter blacklist"
          />
        </div>
        {!blacklist ? (
          <Loading />
        ) : blacklist.entries.length === 0 ? (
          <p className="p-4 text-sm text-ink-dim">
            <ShieldOff size={14} className="mr-1 inline" aria-hidden /> Nothing blocked.
          </p>
        ) : (
          <ul className="scroll-thin max-h-[360px] divide-y divide-line overflow-y-auto">
            {blacklist.entries.map((b) => (
              <li key={b.id} className="flex items-center gap-2 px-3 py-2">
                <span className="min-w-0 flex-1 truncate text-sm text-heading">
                  {b.display_name}
                </span>
                <span className="pill font-num uppercase text-ink-faint">{b.kind}</span>
                <ConfirmActionButton
                  onConfirm={() => api.removeBlacklistEntry(b.id).then(load).catch((e) => setError(e instanceof Error ? e.message : "Failed to unblock"))}
                  label={<X size={14} />}
                  confirmLabel="UNBLOCK?"
                  className="btn btn-ghost !min-h-0 p-2"
                  ariaLabel={`Unblock ${b.display_name}`}
                  confirmAriaLabel={`Confirm unblocking ${b.display_name}`}
                />
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function HardwarePanel() {
  const [hw, setHw] = useState<HardwareResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const loadHw = useCallback(() => {
    setError(null);
    api
      .hardware()
      .then(setHw)
      .catch((err: unknown) => err instanceof Error && setError(err.message));
  }, []);

  useEffect(loadHw, [loadHw]);

  const reset = async () => {
    try {
      const res = await api.resetEmbeddings(true);
      setStatus(`Cleared ${res.cleared} embeddings`);
    } catch (err) {
      if (err instanceof Error) setError(err.message);
    }
  };

  if (error) return <ErrorState message={error} onRetry={loadHw} />;
  if (!hw) return <Loading label="PROBING HARDWARE…" />;

  const rows: [string, string][] = [
    ["TORCH", hw.torch_version ?? "—"],
    ["CUDA", hw.cuda_available ? `available${hw.cuda_version ? ` (${hw.cuda_version})` : ""}` : "not available"],
    ["GPU", hw.gpu_name ?? "—"],
    ["VRAM", hw.vram_total_mb != null ? `${(hw.vram_total_mb / 1024).toFixed(1)} GB` : "—"],
    ["FFMPEG", hw.has_ffmpeg ? hw.ffmpeg_version ?? "available" : "missing"],
    ["RAM", hw.ram_total_mb != null ? `${(hw.ram_total_mb / 1024).toFixed(1)} GB` : "—"],
    ["GPU READY", hw.gpu_ready ? "yes" : "no"],
  ];

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <section className="panel">
        <PanelHead title="HARDWARE REPORT" />
        <dl className="divide-y divide-line">
          {rows.map(([k, v]) => (
            <div key={k} className="flex items-center justify-between gap-3 px-3 py-2">
              <dt className="eyebrow">{k}</dt>
              <dd className="font-num truncate text-sm text-heading">{v}</dd>
            </div>
          ))}
        </dl>
      </section>
      <section className="panel self-start border-danger/40">
        <PanelHead title="DANGER ZONE" />
        <div className="flex flex-wrap items-center gap-3 p-3">
          <p className="min-w-[180px] flex-1 text-xs text-ink-dim">
            Rebuild the embedding index from scratch. Tracks and metadata stay; similarity needs a
            new index run.
          </p>
          <ConfirmActionButton
            onConfirm={reset}
            label={
              <>
                <RotateCcw size={14} /> RESET EMBEDDINGS
              </>
            }
            confirmLabel="CONFIRM RESET?"
            className="btn btn-danger"
          />
        </div>
        {status ? (
          <p className="px-3 pb-3 font-mono text-xs text-accent" role="status">
            {status}
          </p>
        ) : null}
      </section>
    </div>
  );
}

export function LibraryView() {
  const [sub, setSub] = useState<SubTab>("artists");
  const TABS: { id: SubTab; label: string }[] = [
    { id: "artists", label: "ARTISTS HUB" },
    { id: "cleanup", label: "TRACKS CLEANUP" },
    { id: "seeds", label: "SEEDS & BLACKLIST" },
    { id: "hardware", label: "HARDWARE" },
  ];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h1 className="text-2xl font-bold tracking-[-0.02em] text-heading">Library</h1>
        <div
          role="tablist"
          aria-label="Library sections"
          className="lib-tabs -mx-1 max-w-full px-1 py-1"
        >
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={sub === t.id}
              data-libmode={t.id}
              onClick={() => setSub(t.id)}
              className="btn shrink-0"
              style={
                sub === t.id
                  ? {
                      borderColor: "var(--color-accent)",
                      color: "var(--color-heading)",
                      background: "color-mix(in srgb, var(--color-accent) 30%, transparent)",
                    }
                  : undefined
              }
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>
      {sub === "artists" ? (
        <ArtistsHub onOpenCleanup={() => setSub("cleanup")} />
      ) : null}
      {sub === "cleanup" ? <CleanupWizard /> : null}
      {sub === "seeds" ? <SeedsBlacklist /> : null}
      {sub === "hardware" ? <HardwarePanel /> : null}
    </div>
  );
}
