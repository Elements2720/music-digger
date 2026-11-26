import type { Track } from "../types/apiTypes";
import type { M3u8PathMode } from "../stores/settingsStore";

export interface M3u8Options {
  pathMode: M3u8PathMode;
  pathPrefix: string;
  includeMetadata: boolean;
}

const AUDIO_EXT = /\.(mp3|m4a|aac|flac|wav|aiff|ogg|opus)$/i;

function basename(path: string): string {
  const normalised = path.replace(/\\/g, "/");
  const cut = normalised.lastIndexOf("/");
  return cut === -1 ? normalised : normalised.slice(cut + 1);
}

function toPath(rawPath: string, options: M3u8Options): string {
  const normalised = rawPath.replace(/\\/g, "/");
  if (options.pathMode === "relative") {
    const prefix = options.pathPrefix.trim().replace(/\/+$/, "");
    return prefix ? `${prefix}/${basename(normalised)}` : basename(normalised);
  }
  if (/^(https?:\/\/|file:\/\/|\/api\/)/i.test(normalised)) return normalised;
  return /^[a-zA-Z]:\//.test(normalised)
    ? `file:///${normalised}`
    : `file://${normalised.startsWith("/") ? "" : "/"}${normalised}`;
}

function metaLine(track: Track): string {
  const seconds =
    typeof track.duration_seconds === "number" && track.duration_seconds > 0
      ? Math.round(track.duration_seconds)
      : -1;
  const name = track.artist ? `${track.artist} - ${track.title}` : track.title;
  return `#EXTINF:${seconds},${name}`;
}

/** Build an .m3u8 for the crate. Tracks without a local file are skipped. */
export function buildM3u8(
  tracks: Track[],
  options: M3u8Options,
): { text: string; skipped: number } {
  const playable = tracks.filter((t) => t.local_path && AUDIO_EXT.test(t.local_path));
  const lines = ["#EXTM3U"];
  for (const track of playable) {
    if (options.includeMetadata) lines.push(metaLine(track));
    lines.push(toPath(track.local_path as string, options));
  }
  return { text: `${lines.join("\n")}\n`, skipped: tracks.length - playable.length };
}

/**
 * Re-write a playlist the backend already generated so it follows the local
 * export settings (path style and metadata tags).
 */
export function remapM3u8(text: string, options: M3u8Options): string {
  const out: string[] = ["#EXTM3U"];
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#EXTM3U")) continue;
    if (line.startsWith("#")) {
      if (line.startsWith("#EXTINF") && !options.includeMetadata) continue;
      out.push(line);
      continue;
    }
    out.push(toPath(line, options));
  }
  return `${out.join("\n")}\n`;
}

export function downloadPlaylist(filename: string, text: string): void {
  const blob = new Blob([text], { type: "audio/x-mpegurl" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename.endsWith(".m3u8") ? filename : `${filename}.m3u8`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
