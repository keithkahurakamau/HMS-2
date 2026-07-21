import { render } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import PartographChart, { xForHours, yForDilation, alertLinePoints, actionLinePoints } from './PartographChart';

describe('partograph geometry', () => {
  it('maps hours to x linearly across the 12h plot', () => {
    expect(xForHours(0)).toBe(60);
    expect(xForHours(12)).toBe(700);
    expect(xForHours(6)).toBeCloseTo(380);
  });

  it('maps dilation to inverted y', () => {
    expect(yForDilation(0)).toBe(300);
    expect(yForDilation(10)).toBe(40);
  });

  it('alert line runs from 4cm@0h to 10cm@6h; action line is +4h parallel', () => {
    const alert = alertLinePoints();
    expect(alert.x1).toBe(xForHours(0));
    expect(alert.y1).toBe(yForDilation(4));
    expect(alert.x2).toBe(xForHours(6));
    expect(alert.y2).toBe(yForDilation(10));
    const action = actionLinePoints();
    expect(action.x1).toBe(xForHours(4));
    expect(action.y1).toBe(yForDilation(4));
    expect(action.x2).toBe(xForHours(10));
    expect(action.y2).toBe(yForDilation(10));
  });

  it('renders superseded points hollow', () => {
    const activeStart = '2026-07-10T06:00:00Z';
    const entries = [
      { entry_id: 1, recorded_at: '2026-07-10T07:00:00Z', cervical_dilation_cm: 5, superseded: true },
      { entry_id: 2, recorded_at: '2026-07-10T07:00:00Z', cervical_dilation_cm: 6, superseded: false },
    ];
    const { container } = render(<PartographChart entries={entries} activeStart={activeStart} />);
    const points = container.querySelectorAll('circle[data-kind="dilation"]');
    expect(points).toHaveLength(2);
    expect(points[0].getAttribute('fill')).toBe('none');
    expect(points[1].getAttribute('fill')).not.toBe('none');
  });
});
