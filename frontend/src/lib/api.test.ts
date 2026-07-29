import { afterEach, describe, expect, it } from 'vitest';
import { api } from './api';

describe('api.audioUrl', () => {
  afterEach(() => {
    delete window.KOTOBA_AUTH_TOKEN;
  });

  it('returns a bare path when no auth token is set', () => {
    expect(api.audioUrl(9)).toBe('/api/episodes/9/audio');
  });

  it('appends the token as a query param when set', () => {
    window.KOTOBA_AUTH_TOKEN = 'sec ret';
    expect(api.audioUrl(9)).toBe('/api/episodes/9/audio?token=sec%20ret');
  });
});
