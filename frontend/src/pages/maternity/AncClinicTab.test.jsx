import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import AncClinicTab from './AncClinicTab';
import * as api from './api';

vi.mock('./api');

describe('AncClinicTab', () => {
  beforeEach(() => {
    api.listEpisodes.mockResolvedValue([
      { episode_id: 1, patient_name: 'Wanjiku, Grace', gravida: 2, para: 1,
        edd: '2026-12-06', status: 'Active' },
    ]);
  });

  it('lists active episodes', async () => {
    render(<AncClinicTab />);
    expect(await screen.findByText(/Wanjiku, Grace/)).toBeInTheDocument();
    expect(screen.getByText(/G2 P1/)).toBeInTheDocument();
  });

  it('submits an ANC visit for the selected episode', async () => {
    api.getEpisode.mockResolvedValue({
      episode_id: 1, patient_name: 'Wanjiku, Grace', gravida: 2, para: 1,
      status: 'Active', anc_visits: [], pnc_visits: [], deliveries: [], labor: [],
    });
    api.createAncVisit.mockResolvedValue({ visit_id: 9, visit_number: 1 });
    const user = userEvent.setup();
    render(<AncClinicTab />);
    await user.click(await screen.findByText(/Wanjiku, Grace/));
    await user.click(await screen.findByRole('button', { name: /new anc visit/i }));
    await user.type(screen.getByLabelText(/visit date/i), '2026-07-10');
    await user.click(screen.getByRole('button', { name: /save visit/i }));
    await waitFor(() => expect(api.createAncVisit).toHaveBeenCalledWith(1,
      expect.objectContaining({ visit_date: '2026-07-10' })));
  });
});
