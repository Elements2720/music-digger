import type {
  ArtistSummary,
  Match,
  TasteRankedMatch,
  Track,
} from "../types/apiTypes";

export const fmtBpm = (bpm: number | null | undefined): string =>
  bpm == null ? "—" : `${Math.round(bpm * 100) / 100}`;

export const fmtClock = (sec: number | null | undefined): string => {
  if (sec == null || !Number.isFinite(sec)) return "0:00";
  const s = Math.max(0, Math.floor(sec));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};

export const fmtPercent = (v: number | null | undefined): string =>
  v == null ? "—" : `${Math.round(v)}%`;

export const fmtCount = (n: number | null | undefined): string =>
  n == null ? "—" : n.toLocaleString("en-US");

export const artworkFor = (t: {
  artwork_url?: string | null;
  title: string;
  artist: string;
}): string | null => t.artwork_url || null;

export function initials(t: { title: string; artist: string }): string {
  const src = `${t.artist} ${t.title}`.trim();
  const parts = src.split(/\s+/).slice(0, 2);
  return parts.map((p) => p[0]?.toUpperCase() ?? "").join("") || "??";
}

export function isHeard(t: Track | { id: string }, heard: Set<string>): boolean {
  return heard.has(t.id);
}

export function matchPercent(m: Match): string {
  return fmtPercent(m.similarity * 100);
}

export function tastePercent(t: TasteRankedMatch): string {
  return fmtPercent(t.taste_percent);
}

export function artistTaste(a: ArtistSummary): string {
  return fmtPercent(a.taste_match_percent);
}

/** Stable hue from a string, for deterministic artwork placeholders. */
export function hueOf(seed: string): number {
  let h = 0;
  for (let i = 0; i < seed.length; i += 1) {
    h = (h * 31 + seed.charCodeAt(i)) % 360;
  }
  return h;
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}
