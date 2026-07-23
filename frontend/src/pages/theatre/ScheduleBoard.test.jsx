import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import ScheduleBoard from './ScheduleBoard';
import * as api from './api';

vi.mock('./api');

describe('ScheduleBoard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getBoard.mockResolvedValue({
      date: '2026-07-23',
      rooms: [{
        room_id: 1, name: 'Theatre 1',
        cases: [{ case_id: 5, patient_name: 'Otieno, Sam', procedure_name: 'Appendectomy', status: 'InTheatre' }],
      }],
      unassigned: [],
    });
  });

  it('renders rooms and their cases', async () => {
    render(<ScheduleBoard />);
    expect(await screen.findByText(/theatre schedule/i)).toBeInTheDocument();
    expect(screen.getByText('Theatre 1')).toBeInTheDocument();
    expect(screen.getByText(/Otieno, Sam/)).toBeInTheDocument();
  });
});
