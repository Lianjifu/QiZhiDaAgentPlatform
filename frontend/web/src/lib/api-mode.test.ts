import { describe, expect, it } from 'vitest';
import { apiBaseURL, runtimeConfig } from './api-mode';

describe('api-mode', () => {
  it('defaults to the development environment', () => {
    expect(runtimeConfig().environment).toBe('development');
  });

  it('apiBaseURL uses same-origin proxy in DEV for loopback bases', () => {
    expect(typeof apiBaseURL()).toBe('string');
    expect(apiBaseURL()).toBe('');
  });
});
