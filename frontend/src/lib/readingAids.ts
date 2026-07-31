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
