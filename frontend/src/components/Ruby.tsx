import type { Segment } from '../lib/types';

const WORD_RE = /\p{L}/u;

interface RubyProps {
  segments: Segment[];
  showFurigana: boolean;
  onWordClick?: (word: string, e: React.MouseEvent) => void;
}

export function Ruby({ segments, showFurigana, onWordClick }: RubyProps) {
  return (
    <>
      {segments.map((seg, i) => {
        const clickable = onWordClick && WORD_RE.test(seg.base);
        const handleClick = clickable
          ? (e: React.MouseEvent) => {
              e.stopPropagation();
              onWordClick!(seg.base, e);
            }
          : undefined;
        const wordStyle: React.CSSProperties | undefined = clickable ? { cursor: 'pointer' } : undefined;
        return seg.reading && showFurigana ? (
          <ruby key={i}>
            <span onClick={handleClick} style={wordStyle} data-testid={clickable ? 'word' : undefined}>
              {seg.base}
            </span>
            <rt style={{ fontSize: '0.55em', color: 'rgba(32,30,26,.55)' }}>{seg.reading}</rt>
          </ruby>
        ) : (
          <span key={i} onClick={handleClick} style={wordStyle} data-testid={clickable ? 'word' : undefined}>
            {seg.base}
          </span>
        );
      })}
    </>
  );
}
