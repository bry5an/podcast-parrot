import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Ruby } from './Ruby';

describe('Ruby', () => {
  it('renders a ruby/rt pair for segments with a reading when furigana is on', () => {
    render(<Ruby segments={[{ base: '日本語', reading: 'にほんご' }]} showFurigana />);
    expect(screen.getByText('日本語').closest('ruby')).toBeInTheDocument();
    expect(screen.getByText('にほんご').tagName).toBe('RT');
  });

  it('falls back to a plain span for segments without a reading', () => {
    render(<Ruby segments={[{ base: 'です', reading: '' }]} showFurigana />);
    expect(screen.getByText('です').tagName).toBe('SPAN');
  });

  it('renders plain spans (no <rt>) when furigana is off, even with a reading', () => {
    render(<Ruby segments={[{ base: '日本語', reading: 'にほんご' }]} showFurigana={false} />);
    expect(screen.getByText('日本語').tagName).toBe('SPAN');
    expect(screen.queryByText('にほんご')).not.toBeInTheDocument();
  });
});
