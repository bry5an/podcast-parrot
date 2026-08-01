import type { LearningLanguage } from './types';

export interface Swatch {
  art: string;
  shadow: string;
}

export const PALETTE: Swatch[] = [
  { art: 'linear-gradient(135deg,oklch(0.66 0.05 235),oklch(0.56 0.06 250))', shadow: 'oklch(0.56 0.06 250 / 0.4)' },
  { art: 'linear-gradient(135deg,oklch(0.64 0.09 62),oklch(0.56 0.1 45))', shadow: 'oklch(0.56 0.1 45 / 0.4)' },
  { art: 'linear-gradient(135deg,oklch(0.6 0.08 155),oklch(0.52 0.09 165))', shadow: 'oklch(0.52 0.09 165 / 0.4)' },
  { art: 'linear-gradient(135deg,oklch(0.62 0.1 350),oklch(0.54 0.11 5))', shadow: 'oklch(0.54 0.11 5 / 0.4)' },
  { art: 'linear-gradient(135deg,oklch(0.58 0.09 285),oklch(0.5 0.1 300))', shadow: 'oklch(0.5 0.1 300 / 0.4)' },
];

export const LANGUAGE_META: Record<
  LearningLanguage,
  { flag: string; title: string; sub: string }
> = {
  ja: { flag: '🇯🇵', title: 'Japanese', sub: '日本語' },
  en: { flag: '🇺🇸', title: 'English', sub: 'English' },
  es: { flag: '🇪🇸', title: 'Spanish', sub: 'Español' },
  fr: { flag: '🇫🇷', title: 'French', sub: 'Français' },
  ko: { flag: '🇰🇷', title: 'Korean', sub: '한국어' },
};
