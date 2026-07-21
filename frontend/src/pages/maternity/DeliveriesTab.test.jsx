import { render, screen, waitFor, within } from '@testing-library/react';
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

  it('submits a PNC visit for the selected delivered episode, omitting empty optional numeric fields', async () => {
    api.createPncVisit.mockResolvedValue({ visit_id: 3, visit_number: 1 });
    api.getEpisode.mockResolvedValue({
      episode_id: 2, patient_name: 'Atieno, Mary', status: 'Delivered',
      anc_visits: [], pnc_visits: [], labor: [], deliveries: [],
    });
    const user = userEvent.setup();
    render(<DeliveriesTab />);
    await user.click(await screen.findByText(/Atieno, Mary/));
    await user.click(await screen.findByRole('button', { name: /new pnc visit/i }));
    await user.type(screen.getByLabelText(/visit date/i), '2026-07-15');
    await user.click(screen.getByRole('button', { name: /save visit/i }));
    await waitFor(() => expect(api.createPncVisit).toHaveBeenCalledWith(2,
      expect.objectContaining({ visit_date: '2026-07-15' })));
    const [, payload] = api.createPncVisit.mock.calls[0];
    expect(payload).not.toHaveProperty('bp_systolic');
    expect(payload).not.toHaveProperty('bp_diastolic');
    expect(payload).not.toHaveProperty('baby_weight_g');
  });

  // Regression: the ANC tab only lists Active episodes, so a Delivered
  // episode was previously unclosable from anywhere in the UI — the
  // lifecycle never terminated after delivery.
  it('closes a delivered episode from the delivery detail panel', async () => {
    api.getEpisode.mockResolvedValue({
      episode_id: 2, patient_name: 'Atieno, Mary', status: 'Delivered',
      anc_visits: [], pnc_visits: [], labor: [], deliveries: [],
    });
    api.closeEpisode.mockResolvedValue({ episode_id: 2, status: 'Closed' });
    const user = userEvent.setup();
    render(<DeliveriesTab />);
    await user.click(await screen.findByText(/Atieno, Mary/));
    await user.click(await screen.findByRole('button', { name: /close episode/i }));
    const dialog = await screen.findByRole('dialog', { name: /close episode/i });
    await user.click(within(dialog).getByRole('button', { name: /confirm close/i }));
    await waitFor(() =>
      expect(api.closeEpisode).toHaveBeenCalledWith(2, expect.objectContaining({ status: 'Closed' }))
    );
    // The closed episode is neither Active nor Delivered, so the detail
    // panel must clear rather than linger on an episode nobody can act on.
    await waitFor(() =>
      expect(screen.queryByRole('region', { name: /delivery detail/i })).not.toBeInTheDocument()
    );
  });

  it('offers no close control when the fetched episode is not Delivered', async () => {
    // A stale Delivered list can hand us an episode whose status has since
    // moved on. The Close control keys off the freshly-fetched status, not
    // the list the row came from.
    api.getEpisode.mockResolvedValue({
      episode_id: 2, patient_name: 'Atieno, Mary', status: 'Active',
      anc_visits: [], pnc_visits: [], labor: [], deliveries: [],
    });
    const user = userEvent.setup();
    render(<DeliveriesTab />);
    await user.click(await screen.findByText(/Atieno, Mary/));
    await screen.findByRole('button', { name: /new pnc visit/i });
    expect(screen.queryByRole('button', { name: /close episode/i })).not.toBeInTheDocument();
  });
});
