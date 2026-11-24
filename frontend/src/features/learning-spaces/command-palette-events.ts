/** Lets any button open the command palette without sharing React state. */
const EVENT = "axonweave:open-command-palette";

export function openCommandPalette(): void {
  window.dispatchEvent(new Event(EVENT));
}

export function onOpenCommandPalette(cb: () => void): () => void {
  window.addEventListener(EVENT, cb);
  return () => window.removeEventListener(EVENT, cb);
}
