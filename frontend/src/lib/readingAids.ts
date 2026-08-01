export type TextSize = 'S' | 'M' | 'L';

export const TEXT_SIZE_PX: Record<TextSize, number> = { S: 15, M: 18, L: 21 };

export const DEFAULT_TEXT_SIZE: TextSize = 'M';

const TEXT_SIZE_STORAGE_KEY = 'kotoba.transcriptTextSize';

export function loadTextSize(): TextSize {
  const raw = localStorage.getItem(TEXT_SIZE_STORAGE_KEY);
  return raw === 'S' || raw === 'M' || raw === 'L' ? raw : DEFAULT_TEXT_SIZE;
}

export function saveTextSize(size: TextSize): void {
  localStorage.setItem(TEXT_SIZE_STORAGE_KEY, size);
}

export const DEFAULT_SHOW_ROMAJI = false;

const SHOW_ROMAJI_STORAGE_KEY = 'kotoba.showRomaji';

export function loadShowRomaji(): boolean {
  return localStorage.getItem(SHOW_ROMAJI_STORAGE_KEY) === 'true';
}

export function saveShowRomaji(value: boolean): void {
  localStorage.setItem(SHOW_ROMAJI_STORAGE_KEY, String(value));
}

export const DEFAULT_DIM_INACTIVE = true;

const DIM_INACTIVE_STORAGE_KEY = 'kotoba.dimInactiveLines';

export function loadDimInactiveLines(): boolean {
  const raw = localStorage.getItem(DIM_INACTIVE_STORAGE_KEY);
  return raw === null ? DEFAULT_DIM_INACTIVE : raw === 'true';
}

export function saveDimInactiveLines(value: boolean): void {
  localStorage.setItem(DIM_INACTIVE_STORAGE_KEY, String(value));
}
