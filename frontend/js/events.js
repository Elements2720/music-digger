/* Tiny pub/sub bus. Views communicate through events, never through each other. */

const handlers = new Map();

export function on(event, fn) {
  if (!handlers.has(event)) handlers.set(event, new Set());
  handlers.get(event).add(fn);
  return () => off(event, fn);
}

export function off(event, fn) {
  handlers.get(event)?.delete(fn);
}

export function emit(event, payload) {
  handlers.get(event)?.forEach((fn) => {
    try {
      fn(payload);
    } catch (err) {
      console.error(`[events] handler for ${event} failed`, err);
    }
  });
}
