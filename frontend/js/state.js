/* Shared UI state plus a tiny event bus. No framework, no build step. */

export const state = {
  tab: "run",
  reference: null,
  lastJob: null,
  stats: null,
};

const handlers = new Map();

export function on(event, handler) {
  if (!handlers.has(event)) handlers.set(event, new Set());
  handlers.get(event).add(handler);
  return () => handlers.get(event)?.delete(handler);
}

export function emit(event, payload) {
  for (const handler of handlers.get(event) ?? []) {
    try {
      handler(payload);
    } catch (error) {
      console.error(`handler for ${event} failed`, error);
    }
  }
}
