export type Theme = 'warm' | 'light' | 'dark';

export const DEFAULT_THEME: Theme = 'warm';

const THEME_STORAGE_KEY = 'kotoba.theme';

export function loadTheme(): Theme {
  const raw = localStorage.getItem(THEME_STORAGE_KEY);
  return raw === 'warm' || raw === 'light' || raw === 'dark' ? raw : DEFAULT_THEME;
}

export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
}

export function saveTheme(theme: Theme): void {
  localStorage.setItem(THEME_STORAGE_KEY, theme);
  applyTheme(theme);
}
