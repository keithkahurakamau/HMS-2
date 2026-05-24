import { describe, it, expect } from 'vitest';

describe('test infra smoke', () => {
  it('boots vitest + jest-dom matchers', () => {
    const el = document.createElement('div');
    el.textContent = 'hello';
    document.body.appendChild(el);
    expect(el).toHaveTextContent('hello');
    document.body.removeChild(el);
  });
});
