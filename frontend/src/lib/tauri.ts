// The frontend also runs as a plain web page (`npm run dev`, vitest, a
// browser tab pointed at the backend directly) where no Tauri host exists,
// so every desktop integration in this module is a no-op there instead of
// throwing.
export const isTauri = (): boolean => '__TAURI_INTERNALS__' in window;

export async function invokeTauri<T = void>(cmd: string, args?: Record<string, unknown>): Promise<T | undefined> {
  if (!isTauri()) return undefined;
  const { invoke } = await import('@tauri-apps/api/core');
  return invoke<T>(cmd, args);
}

export async function listenTauri<T = unknown>(event: string, handler: (payload: T) => void): Promise<() => void> {
  if (!isTauri()) return () => {};
  const { listen } = await import('@tauri-apps/api/event');
  return listen<T>(event, (e) => handler(e.payload));
}
