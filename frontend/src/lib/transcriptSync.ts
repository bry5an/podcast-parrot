import type { Sentence } from './types';

// Binary-searches ordered, non-overlapping [start_time, end_time) sentences
// for the one containing `t`; -1 if `t` falls in a gap between sentences.
export function findActiveIndex(sentences: Sentence[], t: number): number {
  let lo = 0;
  let hi = sentences.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    const s = sentences[mid];
    if (t < s.start_time) hi = mid - 1;
    else if (t >= s.end_time) lo = mid + 1;
    else return mid;
  }
  return -1;
}
