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

export const DIRECTION_META: Record<
  'en_ja' | 'ja_en',
  { flag: string; code: string; title: string; sub: string }
> = {
  en_ja: { flag: '🇯🇵', code: 'EN → JA', title: 'Japanese', sub: '日本語 · native English' },
  ja_en: { flag: '🇺🇸', code: 'JA → EN', title: 'English', sub: '英語 · native Japanese' },
};
