import { render, screen, waitFor, within } from '@testing-library/react';
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

  it('closes an episode with a status and reason, then refreshes the list', async () => {
    api.getEpisode.mockResolvedValue({
      episode_id: 1, patient_name: 'Wanjiku, Grace', gravida: 2, para: 1,
      status: 'Active', anc_visits: [], pnc_visits: [], deliveries: [], labor: [],
    });
    api.closeEpisode.mockResolvedValue({ episode_id: 1, status: 'Closed' });
    const user = userEvent.setup();
    render(<AncClinicTab />);
    await screen.findByText(/Wanjiku, Grace/);
    // Mock call counts persist across tests in this file (no clearMocks), so
    // compare against a snapshot taken here rather than an absolute count.
    const listCallsBeforeClose = api.listEpisodes.mock.calls.length;
    await user.click(screen.getByText(/Wanjiku, Grace/));
    await user.click(await screen.findByRole('button', { name: /close episode/i }));
    const dialog = await screen.findByRole('dialog', { name: /close episode/i });
    await user.type(within(dialog).getByLabelText(/reason/i), 'Miscarriage');
    await user.click(within(dialog).getByRole('button', { name: /confirm close/i }));
    await waitFor(() => expect(api.closeEpisode).toHaveBeenCalledWith(1,
      expect.objectContaining({ status: 'Closed', reason: 'Miscarriage' })));
    await waitFor(() => expect(api.listEpisodes.mock.calls.length).toBeGreaterThan(listCallsBeforeClose));
    // The now-closed episode's detail panel clears rather than re-showing stale data.
    expect(await screen.findByText(/select an episode to view visits/i)).toBeInTheDocument();
  });
});
