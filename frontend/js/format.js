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

const CAMELOT_KEYS = {
  "1A": "Abm",
  "1B": "B",
  "2A": "Ebm",
  "2B": "F#",
  "3A": "Bbm",
  "3B": "Db",
  "4A": "Fm",
  "4B": "Ab",
  "5A": "Cm",
  "5B": "Eb",
  "6A": "Gm",
  "6B": "Bb",
  "7A": "Dm",
  "7B": "F",
  "8A": "Am",
  "8B": "C",
  "9A": "Em",
  "9B": "G",
  "10A": "Bm",
  "10B": "D",
  "11A": "F#m",
  "11B": "A",
  "12A": "C#m",
  "12B": "E",
};

export function camelotMeta(key) {
  if (!key || typeof key !== "string") {
    return {
      valid: false,
      code: key ? String(key).trim() : "—",
      number: null,
      mode: null,
      letter: null,
      musicalKey: null,
      compatible: null,
      title: key ? `Key: ${key}` : "No key detected",
      classes: "camelot-chip ck-unknown",
    };
  }

  const trimmed = key.trim();
  const match = trimmed.match(/^(1[0-2]|[1-9])([abAB])$/);
  if (!match) {
    return {
      valid: false,
      code: trimmed,
      number: null,
      mode: null,
      letter: null,
      musicalKey: null,
      compatible: null,
      title: `Key: ${trimmed}`,
      classes: "camelot-chip ck-unknown",
    };
  }

  const num = parseInt(match[1], 10);
  const letter = match[2].toUpperCase();
  const mode = letter.toLowerCase();
  const code = `${num}${letter}`;
  const musicalKey = CAMELOT_KEYS[code] || "";

  const prev = num === 1 ? 12 : num - 1;
  const next = num === 12 ? 1 : num + 1;
  const relMode = letter === "A" ? "B" : "A";
  const compatible = `${prev}${letter}, ${num}${letter}, ${next}${letter}, ${num}${relMode}`;
  const title = `${code} (${musicalKey}) · Mix with: ${compatible}`;

  return {
    valid: true,
    code,
    number: num,
    mode,
    letter,
    musicalKey,
    compatible,
    title,
    classes: `camelot-chip ck-${num} ck-${mode}`,
  };
}

export function camelotAttrs(key, extraClass = "") {
  const meta = camelotMeta(key);
  const cls = [meta.classes, extraClass].filter(Boolean).join(" ");
  if (meta.valid) {
    return `class="${cls}" data-camelot-num="${meta.number}" data-camelot-mode="${meta.mode}" title="${meta.title}"`;
  }
  return `class="${cls}" title="${meta.title}"`;
}
