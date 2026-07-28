import type { Segment } from '../lib/types';

export function Ruby({ segments, showFurigana }: { segments: Segment[]; showFurigana: boolean }) {
  return (
    <>
      {segments.map((seg, i) =>
        seg.reading && showFurigana ? (
          <ruby key={i}>
            {seg.base}
            <rt style={{ fontSize: '0.55em', color: 'rgba(32,30,26,.55)' }}>{seg.reading}</rt>
          </ruby>
        ) : (
          <span key={i}>{seg.base}</span>
        ),
      )}
    </>
  );
}
