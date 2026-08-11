import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import RosterTab from './RosterTab';
import * as api from './api';

vi.mock('./api');

describe('RosterTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getRoster.mockResolvedValue({
      date: '2026-07-23', weekday: 'Thu',
      machines: [{
        machine_id: 1, name: 'HD-01', station: 'Station 1', is_active: true,
        current_order: { order_id: 5, patient_name: 'Otieno, Sam', status: 'Connected' },
      }],
      scheduled: [{ schedule_id: 1, patient_id: 5, patient_name: 'Otieno, Sam', pattern: 'MWF', shift: 'Morning' }],
    });
  });

  it('renders chair occupancy and scheduled patients', async () => {
    render(<RosterTab />);
    expect(await screen.findByText(/chair occupancy/i)).toBeInTheDocument();
    expect(screen.getByText('HD-01')).toBeInTheDocument();
    expect(screen.getAllByText(/Otieno, Sam/).length).toBeGreaterThan(0);
  });
});
