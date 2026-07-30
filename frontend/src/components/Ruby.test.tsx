import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
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

  it('fires onWordClick with the word when a word segment is clicked, stopping propagation', () => {
    const onWordClick = vi.fn();
    const onRowClick = vi.fn();
    render(
      <div onClick={onRowClick}>
        <Ruby segments={[{ base: 'Hello', reading: '' }]} showFurigana onWordClick={onWordClick} />
      </div>,
    );
    fireEvent.click(screen.getByText('Hello'));
    expect(onWordClick).toHaveBeenCalledWith('Hello', expect.anything());
    expect(onRowClick).not.toHaveBeenCalled();
  });

  it('does not attach a click handler to punctuation/whitespace segments', () => {
    const onWordClick = vi.fn();
    const { container } = render(
      <Ruby
        segments={[
          { base: 'Hello', reading: '' },
          { base: ', ', reading: '' },
        ]}
        showFurigana
        onWordClick={onWordClick}
      />,
    );
    const punctuationSpan = screen.getByText('Hello').nextSibling as Element;
    expect(punctuationSpan.textContent).toBe(', ');
    expect(container.querySelectorAll('[data-testid="word"]')).toHaveLength(1);
    fireEvent.click(punctuationSpan);
    expect(onWordClick).not.toHaveBeenCalled();
  });
});
