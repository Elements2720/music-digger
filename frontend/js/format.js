/* Formatting helpers shared by rows, the player, and the set views. */

export const PLACEHOLDER =
  "data:image/svg+xml;charset=utf-8," +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64">' +
      '<rect width="64" height="64" rx="6" fill="#202026"/>' +
      '<text x="32" y="42" font-size="26" text-anchor="middle" ' +
      'fill="#ff4d1a" font-family="monospace">\u25c8</text></svg>'
  );

export function fmtTime(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const whole = Math.floor(seconds);
  const minutes = Math.floor(whole / 60);
  const rest = whole % 60;
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

export function fmtClock(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return "00:00:00";
  const whole = Math.floor(seconds);
  const hours = Math.floor(whole / 3600);
  const minutes = Math.floor((whole % 3600) / 60);
  const rest = whole % 60;
  return [hours, minutes, rest]
    .map((part) => String(part).padStart(2, "0"))
    .join(":");
}

export function fmtBpm(bpm) {
  if (bpm === null || bpm === undefined) return null;
  return `${Number(bpm) % 1 === 0 ? Number(bpm) : Number(bpm).toFixed(1)} BPM`;
}

export function fmtRange(start, end) {
  return `${fmtClock(start)} – ${fmtClock(end)}`;
}

export function fmtMemory(mb) {
  if (mb === null || mb === undefined) return "—";
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
  return `${mb} MB`;
}

export function fmtNumber(n) {
  if (n === null || n === undefined || !Number.isFinite(Number(n))) return "0";
  return Number(n).toLocaleString();
}
