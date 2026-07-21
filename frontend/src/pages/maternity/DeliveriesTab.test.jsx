import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import DeliveriesTab from './DeliveriesTab';
import * as api from './api';

vi.mock('./api');

describe('DeliveriesTab', () => {
  beforeEach(() => {
    api.listEpisodes.mockImplementation(({ status }) =>
      Promise.resolve(
        status === 'Delivered'
          ? [{ episode_id: 2, patient_name: 'Atieno, Mary', gravida: 1, para: 1, status: 'Delivered' }]
          : [{ episode_id: 1, patient_name: 'Wanjiku, Grace', gravida: 2, para: 1, status: 'Active' }],
      ));
  });

  it('shows delivered episodes with newborn registration', async () => {
    api.getEpisode.mockResolvedValue({
      episode_id: 2, patient_name: 'Atieno, Mary', status: 'Delivered',
      anc_visits: [], pnc_visits: [], labor: [],
      deliveries: [{
        delivery_id: 5, mode: 'SVD', delivered_at: '2026-07-10T08:30:00Z',
        mother_status: 'Stable', blood_loss_ml: 250,
        newborns: [{ newborn_id: 7, birth_order: 1, sex: 'Female', weight_g: 3200,
                     outcome: 'Live', registered_patient_id: null }],
      }],
    });
    api.registerNewborn.mockResolvedValue({ patient_id: 321 });
    const user = userEvent.setup();
    render(<DeliveriesTab />);
    await user.click(await screen.findByText(/Atieno, Mary/));
    const btn = await screen.findByRole('button', { name: /register as patient/i });
    await user.click(btn);
    await waitFor(() => expect(api.registerNewborn).toHaveBeenCalledWith(7));
  });

  it('opens Record delivery for an active episode and blocks submit with zero newborns', async () => {
    const user = userEvent.setup();
    render(<DeliveriesTab />);
    await user.click(await screen.findByRole('button', { name: /record delivery/i }));
    await user.type(screen.getByLabelText(/delivered at/i), '2026-07-10T08:30');
    // Remove the only newborn row so the form has zero newborns, then try to submit.
    await user.click(screen.getByRole('button', { name: /remove/i }));
    await user.click(screen.getByRole('button', { name: /save delivery/i }));
    expect(screen.getByText(/at least one newborn/i)).toBeInTheDocument();
    expect(api.recordDelivery).not.toHaveBeenCalled();
  });

  it('submits a delivery with a newborn row for the selected active episode', async () => {
    api.recordDelivery.mockResolvedValue({ delivery_id: 9, episode_id: 1 });
    api.getEpisode.mockResolvedValue({
      episode_id: 1, patient_name: 'Wanjiku, Grace', status: 'Active',
      anc_visits: [], pnc_visits: [], labor: [], deliveries: [],
    });
    const user = userEvent.setup();
    render(<DeliveriesTab />);
    await user.click(await screen.findByRole('button', { name: /record delivery/i }));
    await user.type(screen.getByLabelText(/delivered at/i), '2026-07-10T08:30');
    await user.click(screen.getByRole('button', { name: /save delivery/i }));
    await waitFor(() => expect(api.recordDelivery).toHaveBeenCalledWith(1,
      expect.objectContaining({
        mode: 'SVD',
        mother_status: 'Stable',
        newborns: [expect.objectContaining({ sex: 'Male', birth_order: 1 })],
      })));
  });
});
