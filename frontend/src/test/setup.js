import '@testing-library/jest-dom/vitest';
import { afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';

afterEach(() => {
  cleanup();
});

// Polyfills jsdom lacks
if (typeof window !== 'undefined') {
  if (!window.matchMedia) {
    window.matchMedia = (query) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    });
  }
  if (!window.scrollTo) {
    window.scrollTo = vi.fn();
  }
}

// Suppress react-router future-flag warnings during tests
const origError = console.error;
console.error = (...args) => {
  const msg = args[0] ?? '';
  if (typeof msg === 'string' && msg.includes('React Router Future Flag Warning')) {
    return;
  }
  origError(...args);
};
