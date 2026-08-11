import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import SessionBoard from './SessionBoard';
import * as api from './api';

vi.mock('./api');

const baseOrder = (over = {}) => ({
  order_id: 1, patient_name: 'Otieno, Sam', patient_id: 5, treatment_no: 1,
  status: 'Ordered', observations: [], complications: [], adequacy: null, checklist_runs: [],
  ...over,
});

describe('SessionBoard', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('disables Connect until a checklist passes', () => {
    render(<SessionBoard order={baseOrder()} onChanged={() => {}} />);
    expect(screen.getByRole('button', { name: /^connect$/i })).toBeDisabled();
  });

  it('enables Connect once a checklist run has passed', () => {
    render(<SessionBoard order={baseOrder({ checklist_runs: [{ run_id: 1, passed: true }] })} onChanged={() => {}} />);
    expect(screen.getByRole('button', { name: /^connect$/i })).toBeEnabled();
  });

  it('connects and refreshes on Connect click', async () => {
    api.connectOrder.mockResolvedValue({});
    api.getOrder.mockResolvedValue(baseOrder({ status: 'Connected', checklist_runs: [{ run_id: 1, passed: true }] }));
    const onChanged = vi.fn();
    const user = userEvent.setup();
    render(<SessionBoard order={baseOrder({ checklist_runs: [{ run_id: 1, passed: true }] })} onChanged={onChanged} />);
    await user.click(screen.getByRole('button', { name: /^connect$/i }));
    await waitFor(() => expect(api.connectOrder).toHaveBeenCalledWith(1));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(expect.objectContaining({ status: 'Connected' })));
  });

  it('renders the observation timeline when observations exist', () => {
    render(<SessionBoard order={baseOrder({
      status: 'Connected',
      observations: [{ obs_id: 1, bp_systolic: 130, bp_diastolic: 80, pulse: 76, uf_volume_ml: 500, recorded_at: '2026-07-22T09:00:00Z' }],
    })} onChanged={() => {}} />);
    expect(screen.getByText('76')).toBeInTheDocument();
  });
});
