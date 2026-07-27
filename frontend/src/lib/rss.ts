const RSS_URL_PATTERN = /^(https?:\/\/|feed:\/\/)/i;
const RSS_EXTENSION_PATTERN = /\.(xml|rss)(\?|$)/i;

export function looksLikeRssUrl(value: string): boolean {
  const trimmed = value.trim();
  return RSS_URL_PATTERN.test(trimmed) || RSS_EXTENSION_PATTERN.test(trimmed);
}
