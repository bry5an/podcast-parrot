export const DOWNLOAD_ERROR_MESSAGES: Record<string, string> = {
  offline: "Couldn't reach the download server. Check your connection and try again.",
  network: 'The download was interrupted partway through. Try again.',
  disk_space: 'Not enough free disk space.',
  checksum: 'The downloaded file was corrupted. Try again.',
  unknown: 'Something went wrong. Try again.',
};
