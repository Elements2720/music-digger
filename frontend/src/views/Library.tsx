import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CheckSquare, Heart, Plus, RotateCcw, Search, ShieldOff, Sparkles, Trash2, X } from "lucide-react";
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
  EmptyState,
  ErrorState,
  Loading,
  PanelHead,
  TrackRow,
} from "../components/ui";
import { fmtCount, fmtPercent } from "../lib/format";
import { useLikesStore } from "../stores/likesStore";

type SubTab = "artists" | "cleanup" | "seeds" | "hardware";

function ArtistModal({
  summary,
  onClose,
}: {
  summary: ArtistSummary;
  onClose: () => void;
}) {
  const [data, setData] = useState<ArtistTracksResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .artistTracks(summary.artist)
      .then((res) => alive && setData(res))
      .catch((err: unknown) => alive && err instanceof Error && setError(err.message));
    return () => {
      alive = false;
    };
  }, [summary.artist]);

  const heardIds = useLikesStore((s) => s.heardIds);
  const toggleHeard = useLikesStore((s) => s.toggleHeard);
  const tracks = data?.tracks ?? [];
  const allHeard =
    tracks.length > 0 && tracks.every((track) => heardIds.has(track.id));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/70" onClick={onClose} aria-hidden />
      <div
        role="dialog"
        aria-label={`Artist ${summary.artist}`}
        className="panel relative flex max-h-[85vh] w-full max-w-2xl flex-col"
      >
        <div className="panel-head">
          <span className="min-w-0">
            <span className="block truncate text-sm font-semibold text-heading">
              {summary.artist}
            </span>
            <span className="font-num block text-[11px] text-ink-dim">
              {summary.track_count} tracks · {summary.embedded_count} embedded ·{" "}
              {summary.taste_match_percent != null
                ? `${fmtPercent(summary.taste_match_percent)} taste`
                : "no taste score"}
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
              allHeard ? "Unmark this artist's tracks" : "Like this artist's tracks"
            }
            onClick={() => {
              for (const track of tracks) toggleHeard(track.id, !allHeard);
            }}
            title={allHeard ? "Unmark this artist's tracks" : "Like this artist's tracks"}
          >
            <Heart size={13} fill={allHeard ? "currentColor" : "none"} />
            {allHeard ? "Liked" : "Like"}
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
        <div className="scroll-thin min-h-0 flex-1 overflow-y-auto">
          {error ? <ErrorState message={error} /> : null}
          {!data && !error ? <Loading /> : null}
          {data?.tracks.map((t) => (
            <TrackRow key={t.id} track={t} queue={data.tracks} />
          ))}
        </div>
      </div>
    </div>
  );
}

function ArtistsHub() {
  const [q, setQ] = useState("");
  const [likedOnly, setLikedOnly] = useState(false);
  const [data, setData] = useState<ArtistSummary[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<ArtistSummary | null>(null);
  const [genre, setGenre] = useState("");
  const [source, setSource] = useState("");
  const [minYear, setMinYear] = useState("");
  const [sort, setSort] = useState("tracks");
  const [tasteMode, setTasteMode] = useState("both");
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [similar, setSimilar] = useState<SimilarArtistsResponse | null>(null);
  const [similarOpen, setSimilarOpen] = useState(false);
  const heard = useLikesStore((s) => s.heardIds);

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

  const toggleLike = async (a: ArtistSummary) => {
    try {
      if (a.is_liked) await api.unlikeArtist(a.artist);
      else await api.likeArtist(a.artist);
      load();
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
    if (
      !window.confirm(
        `Delete ${checked.size} artist(s) and all their tracks? Add them to the blacklist?`,
      )
    )
      return;
    try {
      const res = await api.bulkDeleteArtists({
        artist_names: [...checked],
        blacklist: true,
        reason: "manual bulk delete",
      });
      setChecked(new Set());
      setError(null);
      load();
      setSimilar(null);
      window.alert(
        `Deleted ${res.artists_deleted} artists / ${res.tracks_deleted} tracks · ${res.blacklisted_count} blacklisted`,
      );
    } catch (err) {
      if (err instanceof Error) setError(err.message);
    }
  };

  const deleteArtist = async (a: ArtistSummary) => {
    if (!window.confirm(`Delete ${a.artist} and all their tracks?`)) return;
    try {
      await api.deleteArtist(a.artist, true, "manual delete");
      setSelected(null);
      load();
    } catch (err) {
      if (err instanceof Error) setError(err.message);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <form
        className="panel flex flex-col gap-2 p-3"
        onSubmit={(e) => {
          e.preventDefault();
          load();
        }}
      >
        <div className="flex flex-wrap gap-2">
        <div className="relative min-w-[180px] flex-1">
          <Search
            size={14}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint"
            aria-hidden
          />
          <input
            className="input pl-10"
            placeholder="Filter artists…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            aria-label="Filter artists"
          />
        </div>
        <button
          type="button"
          className="btn"
          aria-pressed={likedOnly}
          onClick={() => setLikedOnly((v) => !v)}
          style={likedOnly ? { borderColor: "var(--color-accent)", color: "var(--color-accent)" } : undefined}
        >
          LIKED ONLY
        </button>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <input
            className="input max-w-[140px]"
            placeholder="genre"
            value={genre}
            onChange={(e) => setGenre(e.target.value)}
            aria-label="Genre filter"
          />
          <select
            className="input !w-auto"
            value={source}
            onChange={(e) => setSource(e.target.value)}
            aria-label="Source filter"
          >
            <option value="">ANY SOURCE</option>
            <option value="deezer">DEEZER</option>
            <option value="itunes">ITUNES</option>
            <option value="local">LOCAL</option>
          </select>
          <input
            className="input !w-24"
            type="number"
            placeholder="from yr"
            value={minYear}
            onChange={(e) => setMinYear(e.target.value)}
            aria-label="Minimum release year"
          />
          <select
            className="input !w-auto"
            value={sort}
            onChange={(e) => setSort(e.target.value)}
            aria-label="Sort artists"
          >
            <option value="tracks">SORT: TRACKS</option>
            <option value="taste">SORT: TASTE</option>
            <option value="name">SORT: NAME</option>
          </select>
          <select
            className="input !w-auto"
            value={tasteMode}
            onChange={(e) => setTasteMode(e.target.value)}
            aria-label="Taste mode"
          >
            <option value="both">TASTE: BOTH</option>
            <option value="local">TASTE: LOCAL</option>
            <option value="liked">TASTE: LIKED</option>
          </select>
          <button
            type="button"
            className="btn ml-auto"
            aria-expanded={similarOpen}
            onClick={() => {
              const next = !similarOpen;
              setSimilarOpen(next);
              if (next && !similar) {
                api
                  .similarArtists({ limit: 12 })
                  .then(setSimilar)
                  .catch((err: unknown) => err instanceof Error && setError(err.message));
              }
            }}
          >
            <Sparkles size={13} /> LIKE-MINDED
          </button>
        </div>
      </form>

      {similarOpen ? (
        <section className="panel">
          <PanelHead title="ARTISTS LIKE THE ONES YOU LIKE" />
          {!similar ? (
            <Loading />
          ) : similar.items.length === 0 ? (
            <p className="p-4 text-sm text-ink-dim">
              Like a few artists first — this panel suggests neighbours.
            </p>
          ) : (
            <ul className="divide-y divide-line">
              {similar.items.map((a) => (
                <li key={a.artist} className="flex items-center gap-3 px-3 py-2">
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm text-heading">{a.artist}</span>
                    <span className="font-num block text-[11px] text-ink-dim">
                      {a.track_count} tracks
                      {` · ${fmtPercent(a.similarity_percent)} similar`}
                    </span>
                  </span>
                  <Link
                    to={`/dig?mode=foryou&artist=${encodeURIComponent(a.artist)}`}
                    className="btn btn-ghost !min-h-0 px-2 py-2 font-mono text-[10px]"
                  >
                    DIG
                  </Link>
                  <button
                    type="button"
                    className="btn btn-ghost !min-h-0 p-2"
                    onClick={() => {
                      void api.likeArtist(a.artist).then(load);
                    }}
                    aria-label={`Like ${a.artist}`}
                  >
                    <Heart size={15} className="text-ink-faint" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : null}

      {error ? <ErrorState message={error} /> : null}
      {!data ? (
        <Loading label="LOADING ARTISTS…" />
      ) : data.length === 0 ? (
        <EmptyState title="NO ARTISTS" hint="Index or download some tracks first." />
      ) : (
        <div className="panel" data-testid="artist-list">
          <div className="flex flex-wrap items-center gap-2 px-3 py-2">
            <span className="eyebrow">{fmtCount(total)} ARTISTS</span>
            <button
              type="button"
              className="btn btn-ghost !min-h-0 py-1 font-mono text-[10px]"
              onClick={() =>
                setChecked(
                  checked.size === data.length ? new Set() : new Set(data.map((a) => a.artist)),
                )
              }
            >
              <CheckSquare size={13} /> {checked.size === data.length ? "CLEAR" : "SELECT ALL"}
            </button>
            {checked.size > 0 ? (
              <button
                type="button"
                className="btn btn-danger !min-h-0 py-1 font-mono text-[10px]"
                onClick={() => void bulkDelete()}
              >
                <Trash2 size={13} /> DELETE {checked.size} + BLACKLIST
              </button>
            ) : null}
          </div>
          {data.map((a) => (
            <div
              key={a.artist}
              className="flex items-center gap-3 border-b border-line px-3 py-2 last:border-b-0 hover:bg-panel-2/60"
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
                  <span className="font-num block text-[11px] text-ink-dim">
                    {a.track_count} tracks · {a.embedded_count} embedded
                    {a.taste_match_percent != null
                      ? ` · ${fmtPercent(a.taste_match_percent)} taste`
                      : ""}
                  </span>
                </span>
              </button>
              <span className="hidden gap-1 md:flex">
                {a.genres.slice(0, 2).map((g) => (
                  <span key={g} className="pill font-num uppercase text-ink-dim">
                    {g}
                  </span>
                ))}
              </span>
              <Link
                to={`/dig?mode=foryou&artist=${encodeURIComponent(a.artist)}`}
                className="btn btn-ghost !min-h-0 px-2 py-2 font-mono text-[10px]"
                title="Dig tracks by this artist and similar taste"
              >
                DIG
              </Link>
              <button
                type="button"
                className="btn btn-ghost !min-h-0 p-2"
                onClick={() => void toggleLike(a)}
                aria-label={a.is_liked ? `Unlike ${a.artist}` : `Like ${a.artist}`}
                aria-pressed={a.is_liked}
              >
                <Heart
                  size={16}
                  className={a.is_liked ? "heart-on" : "text-ink-faint"}
                  fill={a.is_liked ? "currentColor" : "none"}
                />
              </button>
              <button
                type="button"
                className="btn btn-ghost !min-h-0 p-2 text-danger"
                onClick={() => void deleteArtist(a)}
                aria-label={`Delete ${a.artist}`}
                title="Delete artist and blacklist"
              >
                <Trash2 size={15} />
              </button>
            </div>
          ))}
        </div>
      )}
      {heard.size >= 0 && selected ? (
        <ArtistModal summary={selected} onClose={() => setSelected(null)} />
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
    sample_artists: ArtistSummary[];
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  const runPreview = async () => {
    setBusy(true);
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
    }
  };

  const execute = async () => {
    if (!preview || preview.artist_count === 0) return;
    if (!window.confirm(`Delete ${preview.artist_count} artists (${preview.track_count} tracks)?`))
      return;
    setBusy(true);
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
            className="mt-2 w-full accent-accent"
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
            PREVIEW
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
      {error ? <ErrorState message={error} /> : null}

      <section className="panel self-start">
        <PanelHead
          title={`PENDING SEEDS${seeds ? ` — ${fmtCount(seeds.total)}` : ""}`}
          right={
            <span className="flex flex-wrap gap-1">
              <button
                type="button"
                className="btn btn-ghost !min-h-0 py-1 font-mono text-[10px]"
                onClick={() => {
                  void api.purgeSeeds({ status: "failed" }).then(load);
                }}
              >
                PURGE FAILED
              </button>
              <button
                type="button"
                className="btn btn-ghost !min-h-0 py-1 font-mono text-[10px]"
                onClick={() => {
                  void api.purgeSeeds({ category: "general" }).then(load);
                }}
              >
                PURGE GENERAL
              </button>
              <button
                type="button"
                className="btn btn-danger !min-h-0 py-1 font-mono text-[10px]"
                onClick={() => {
                  if (window.confirm("Clear every pending seed?")) {
                    void api.purgeSeeds({ status: "pending" }).then(load);
                  }
                }}
              >
                PURGE PENDING
              </button>
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
                <button
                  type="button"
                  className="btn btn-ghost !min-h-0 p-2 text-danger"
                  onClick={() => {
                    void api.deleteSeed(s.name).then(load);
                  }}
                  aria-label={`Delete seed ${s.name}`}
                >
                  <Trash2 size={14} />
                </button>
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
                <button
                  type="button"
                  className="btn btn-ghost !min-h-0 p-2"
                  onClick={() => {
                    void api.removeBlacklistEntry(b.id).then(load);
                  }}
                  aria-label={`Unblock ${b.display_name}`}
                >
                  <X size={14} />
                </button>
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

  useEffect(() => {
    api
      .hardware()
      .then(setHw)
      .catch((err: unknown) => err instanceof Error && setError(err.message));
  }, []);

  const reset = async () => {
    if (!window.confirm("Delete every stored embedding? You will need to re-index.")) return;
    try {
      const res = await api.resetEmbeddings(true);
      setStatus(`Cleared ${res.cleared} embeddings`);
    } catch (err) {
      if (err instanceof Error) setError(err.message);
    }
  };

  if (error) return <ErrorState message={error} />;
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
          <button type="button" className="btn btn-danger" onClick={() => void reset()}>
            <RotateCcw size={14} /> RESET EMBEDDINGS
          </button>
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
        <div role="tablist" aria-label="Library sections" className="flex gap-2">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={sub === t.id}
              data-libmode={t.id}
              onClick={() => setSub(t.id)}
              className="btn !min-h-0 py-2"
              style={
                sub === t.id
                  ? { borderColor: "var(--color-accent)", color: "var(--color-accent)" }
                  : undefined
              }
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>
      {sub === "artists" ? <ArtistsHub /> : null}
      {sub === "cleanup" ? <CleanupWizard /> : null}
      {sub === "seeds" ? <SeedsBlacklist /> : null}
      {sub === "hardware" ? <HardwarePanel /> : null}
    </div>
  );
}
