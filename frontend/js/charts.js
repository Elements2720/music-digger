/* SVG charts: BPM histogram and the Camelot harmony wheel. Pure SVG, no libs. */

import { esc } from "./ui.js";

/** Vertical bar histogram from `[{label, track_count}]`. */
export function bpmHistogram(buckets, { width = 560, height = 220 } = {}) {
  const data = (buckets ?? []).filter((b) => Number(b.track_count) > 0);
  if (!data.length) {
    return `<div class="state-block"><span>No BPM data yet — index the catalog first.</span></div>`;
  }
  const maxV = Math.max(...data.map((d) => d.track_count));
  // Bar geometry stays exact against maxV. Axis tick marks are chart labels,
  // not stored track values, so their text is rounded to whole numbers
  // (Math.round) and the left margin scales with the widest tick label so
  // 5-digit counts never clip.
  const pad = { top: 16, right: 8, bottom: 44, left: Math.max(34, String(maxV).length * 8 + 12) };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const step = innerW / data.length;
  const barW = Math.max(6, step * 0.6);

  let bars = "";
  let labels = "";
  data.forEach((d, i) => {
    const h = (d.track_count / maxV) * innerH;
    const x = pad.left + i * step + (step - barW) / 2;
    const y = pad.top + innerH - h;
    const [bpmMin] = String(d.label ?? "").split("-").map(Number);
    const rangeMax = bpmMin && String(d.label ?? "").includes("-") ? bpmMin + 4.999 : null;
    bars += `<rect class="bar" data-bpm-min="${rangeMax ? bpmMin : ""}" data-bpm-max="${rangeMax ? rangeMax : ""}" x="${x}" y="${y}" width="${barW}" height="${h}" rx="2"><title>${esc(d.label)}: ${d.track_count} tracks</title></rect>`;
    const lx = x + barW / 2;
    const ly = pad.top + innerH + 12;
    labels += `<text class="bar-label" x="${lx}" y="${ly}" text-anchor="end" transform="rotate(-40 ${lx} ${ly})">${esc(d.label)}</text>`;
  });

  let grid = "";
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + (innerH * i) / 4;
    grid += `<line class="gridline" x1="${pad.left}" y1="${y}" x2="${width - pad.right}" y2="${y}"/>`;
    grid += `<text x="${pad.left - 6}" y="${y + 3}" text-anchor="end">${Math.round(maxV * (1 - i / 4))}</text>`;
  }

  return `<svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="BPM histogram">
    ${grid}<line class="axis" x1="${pad.left}" y1="${pad.top + innerH}" x2="${width - pad.right}" y2="${pad.top + innerH}"/>
    ${bars}${labels}</svg>`;
}

const SEGMENTS = 12;

function polar(cx, cy, r, deg) {
  const rad = ((deg - 90) * Math.PI) / 180;
  return [cx + r * Math.cos(rad), cy + r * Math.sin(rad)];
}

function annularSector(cx, cy, r0, r1, a0, a1) {
  const [x0, y0] = polar(cx, cy, r1, a0);
  const [x1, y1] = polar(cx, cy, r1, a1);
  const [x2, y2] = polar(cx, cy, r0, a1);
  const [x3, y3] = polar(cx, cy, r0, a0);
  const large = a1 - a0 > 180 ? 1 : 0;
  return (
    `M ${x0} ${y0} A ${r1} ${r1} 0 ${large} 1 ${x1} ${y1} ` +
    `L ${x2} ${y2} A ${r0} ${r0} 0 ${large} 0 ${x3} ${y3} Z`
  );
}

/**
 * Camelot wheel from `[{camelot_key, track_count}]`.
 * `onPick(key)` is called when a segment is clicked.
 */
export function camelotWheel(keys, { size = 340, onPick = null } = {}) {
  // Backend notation is "1B".."12B" / "1A".."12A"; normalize bare numbers to
  // major ("nB") so both rings light up.
  const counts = new Map();
  for (const k of keys ?? []) {
    const raw = String(k.camelot_key ?? "");
    const match = raw.match(/^(\d{1,2})([AB])?$/);
    if (!match) continue;
    const notation = `${Number(match[1])}${match[2] ?? "B"}`;
    counts.set(notation, (counts.get(notation) ?? 0) + Number(k.track_count ?? 0));
  }
  const maxV = Math.max(1, ...counts.values());
  const cx = size / 2;
  const cy = size / 2;
  const rOuter = size / 2 - 8;
  const rInnerMajor = rOuter * 0.56;
  const rInnerMinor = rOuter * 0.3;
  const segDeg = 360 / SEGMENTS;

  let out = `<svg class="chart-svg" style="max-width:${size}px" viewBox="0 0 ${size} ${size}" role="img" aria-label="Camelot wheel">`;

  for (let n = 1; n <= SEGMENTS; n++) {
    const a0 = (n - 1) * segDeg;
    const a1 = n * segDeg - 2;
    const major = counts.get(`${n}B`) ?? 0;
    const minor = counts.get(`${n}A`) ?? 0;
    const idx = n - 1;

    // Major (outer ring) — energy 8..1 mapping per Camelot convention
    const mOpacity = major ? 0.35 + 0.65 * (major / maxV) : 0.08;
    out += `<g class="wheel-segment" data-key="${n}B"><path class="wheel-cell" d="${annularSector(cx, cy, rInnerMajor, rOuter, a0, a1)}" fill="var(--accent)" fill-opacity="${mOpacity}" stroke="#2a3441"/>`;
    const [lx, ly] = polar(cx, cy, (rInnerMajor + rOuter) / 2, a0 + segDeg / 2);
    out += `<text class="wheel-label" x="${lx}" y="${ly}" text-anchor="middle" dominant-baseline="middle">${n}B</text>`;
    out += `<text class="wheel-sub" x="${lx}" y="${ly + 9}" text-anchor="middle" dominant-baseline="middle">${major}</text></g>`;

    // Minor (inner ring)
    const miOpacity = minor ? 0.35 + 0.65 * (minor / maxV) : 0.08;
    out += `<g class="wheel-segment" data-key="${n}A"><path class="wheel-cell" d="${annularSector(cx, cy, rInnerMinor, rInnerMajor - 4, a0, a1)}" fill="var(--info)" fill-opacity="${miOpacity}" stroke="#2a3441"/>`;
    const [mx, my] = polar(cx, cy, (rInnerMinor + rInnerMajor - 4) / 2, a0 + segDeg / 2);
    out += `<text class="wheel-label" x="${mx}" y="${my - 4}" text-anchor="middle" dominant-baseline="middle">${n}A</text>`;
    out += `<text class="wheel-sub" x="${mx}" y="${my + 7}" text-anchor="middle" dominant-baseline="middle">${minor}</text></g>`;
  }
  out += `<text class="wheel-sub" x="${cx}" y="${cy - 10}" text-anchor="middle">catalog keys</text>`;
  out += `<text class="wheel-sub" x="${cx}" y="${cy + 2}" text-anchor="middle">${onPick ? "click a segment" : ""}</text>`;
  out += `</svg>`;
  return out;
}
