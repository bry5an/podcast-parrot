const YOUTUBE_PLAYLIST_URL_PATTERN = /^https?:\/\/(www\.)?youtube\.com\/playlist\?.*\blist=/i;

export function looksLikeYoutubePlaylistUrl(value: string): boolean {
  return YOUTUBE_PLAYLIST_URL_PATTERN.test(value.trim());
}
