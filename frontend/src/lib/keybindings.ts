export type KeybindingAction =
  | 'playPause'
  | 'replaySentence'
  | 'toggleLoop'
  | 'previousSentence'
  | 'nextSentence'
  | 'cycleSpeed';

export type SeekModifier = 'shift' | 'alt' | 'ctrl' | 'meta';

export interface Keymap {
  playPause: string;
  replaySentence: string;
  toggleLoop: string;
  previousSentence: string;
  nextSentence: string;
  cycleSpeed: string;
  seekModifier: SeekModifier;
}

export const DEFAULT_KEYMAP: Keymap = {
  playPause: ' ',
  replaySentence: 'r',
  toggleLoop: 'l',
  previousSentence: 'ArrowLeft',
  nextSentence: 'ArrowRight',
  cycleSpeed: 's',
  seekModifier: 'shift',
};

export const DEFAULT_SEEK_STEP_SECONDS = 5;

const KEYMAP_STORAGE_KEY = 'kotoba.keymap';
const SEEK_STEP_STORAGE_KEY = 'kotoba.seekStepSeconds';

export function loadKeymap(): Keymap {
  try {
    const raw = localStorage.getItem(KEYMAP_STORAGE_KEY);
    if (!raw) return DEFAULT_KEYMAP;
    return { ...DEFAULT_KEYMAP, ...(JSON.parse(raw) as Partial<Keymap>) };
  } catch {
    return DEFAULT_KEYMAP;
  }
}

export function saveKeymap(keymap: Keymap): void {
  localStorage.setItem(KEYMAP_STORAGE_KEY, JSON.stringify(keymap));
}

export function loadSeekStepSeconds(): number {
  const raw = localStorage.getItem(SEEK_STEP_STORAGE_KEY);
  const parsed = raw ? Number(raw) : NaN;
  return Number.isFinite(parsed) && parsed > 0 ? parsed : DEFAULT_SEEK_STEP_SECONDS;
}

export function saveSeekStepSeconds(seconds: number): void {
  localStorage.setItem(SEEK_STEP_STORAGE_KEY, String(seconds));
}

const MODIFIER_LABELS: Record<SeekModifier, string> = {
  shift: '⇧',
  alt: '⌥',
  ctrl: '⌃',
  meta: '⌘',
};

export function formatKeyLabel(key: string): string {
  if (key === ' ') return 'Space';
  if (key === 'ArrowLeft') return '←';
  if (key === 'ArrowRight') return '→';
  if (key.length === 1) return key.toUpperCase();
  return key;
}

export function formatModifierLabel(modifier: SeekModifier): string {
  return MODIFIER_LABELS[modifier];
}

export function isModifierKey(key: string): boolean {
  return key === 'Shift' || key === 'Control' || key === 'Alt' || key === 'Meta';
}

export function modifierFromEvent(e: { shiftKey: boolean; altKey: boolean; ctrlKey: boolean; metaKey: boolean }): SeekModifier | null {
  if (e.shiftKey) return 'shift';
  if (e.altKey) return 'alt';
  if (e.ctrlKey) return 'ctrl';
  if (e.metaKey) return 'meta';
  return null;
}

export function eventMatchesModifier(e: { shiftKey: boolean; altKey: boolean; ctrlKey: boolean; metaKey: boolean }, modifier: SeekModifier): boolean {
  switch (modifier) {
    case 'shift':
      return e.shiftKey;
    case 'alt':
      return e.altKey;
    case 'ctrl':
      return e.ctrlKey;
    case 'meta':
      return e.metaKey;
  }
}

export function normalizeKey(key: string): string {
  return key.length === 1 ? key.toLowerCase() : key;
}
