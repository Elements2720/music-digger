/** Single source of truth for Camelot key colours: 1..12 walk the wheel. */
const HUES = [186, 170, 154, 140, 110, 80, 55, 34, 14, 290, 318, 344] as const;

export type CamelotMode = "A" | "B";

export interface CamelotColor {
  key: string;
  number: number;
  mode: CamelotMode;
  hue: number;
  /** Solid text/border colour, ≥ 4.5:1 on the black canvas. */
  color: string;
  border: string;
  bg: string;
}

export function camelotColor(key: string | null | undefined): CamelotColor | null {
  if (!key) return null;
  const match = /^(\d{1,2})\s*([AB])$/i.exec(key.trim());
  if (!match) return null;
  const number = Number(match[1]);
  if (!Number.isInteger(number) || number < 1 || number > 12) return null;
  const mode = match[2].toUpperCase() as CamelotMode;
  const hue = HUES[number - 1];
  const color =
    mode === "A" ? `hsl(${hue} 70% 60%)` : `hsl(${hue} 88% 74%)`;
  return {
    key: `${number}${mode}`,
    number,
    mode,
    hue,
    color,
    border: `color-mix(in srgb, ${color} 45%, transparent)`,
    bg: `color-mix(in srgb, ${color} 14%, transparent)`,
  };
}

/** The 12 wheel slots, each with its minor (A) and major (B) colour. */
export function camelotWheel(): { number: number; a: CamelotColor; b: CamelotColor }[] {
  return Array.from({ length: 12 }, (_, i) => {
    const number = i + 1;
    return {
      number,
      a: camelotColor(`${number}A`)!,
      b: camelotColor(`${number}B`)!,
    };
  });
}
