/* Inline SVG action icons — crisp on every OS/phone, no font glyphs.
 * Each icon is a 16x16 <svg> using currentColor so buttons recolor it. */

const SVG = (body, { filled = false } = {}) =>
  `<svg width="16" height="16" viewBox="0 0 24 24" ` +
  `${filled ? 'fill="currentColor" stroke="none"' : 'fill="none" stroke="currentColor"'} ` +
  `stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${body}</svg>`;

/** Heart — outline when not liked, solid when liked. */
export const iconHeart = (liked = false) =>
  SVG(
    '<path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>',
    { filled: liked },
  );

/** Solid play triangle. */
export const iconPlay = () =>
  SVG('<path d="M8 5.5v13l11-6.5z"/>', { filled: true });

/** Solid pause bars. */
export const iconPause = () =>
  SVG('<path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z"/>', { filled: true });

/** Download: arrow into tray. */
export const iconDownload = () =>
  SVG('<path d="M12 3v12"/><path d="m6.5 9.5 5.5 5.5 5.5-5.5"/><path d="M4 20h16"/>');

/** Trash can. */
export const iconTrash = () =>
  SVG('<path d="M4 7h16"/><path d="M9 7V4h6v3"/><path d="M6.5 7l1 13h9l1-13"/><path d="M10 11v6M14 11v6"/>');

/** Close X. */
export const iconClose = () => SVG('<path d="M6 6l12 12M18 6L6 18"/>');

/** Music note (artwork placeholder). */
export const iconNote = () =>
  SVG('<circle cx="7" cy="17.5" r="2.5"/><circle cx="17" cy="15.5" r="2.5"/><path d="M9.5 17.5V6l10-2v11.5"/>');

/** Skip to previous / next (solid bars + triangle). */
export const iconPrev = () =>
  SVG('<path d="M6 5h2.5v14H6z"/><path d="M19 5.5v13L9.5 12z"/>', { filled: true });

export const iconNext = () =>
  SVG('<path d="M15.5 5H18v14h-2.5z"/><path d="M5 5.5v13L14.5 12z"/>', { filled: true });

/** Chevron arrows (row move up / down). */
export const iconUp = () => SVG('<path d="m6 14 6-6 6 6"/>');
export const iconDown = () => SVG('<path d="m6 10 6 6 6-6"/>');

