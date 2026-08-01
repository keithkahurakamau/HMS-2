import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import OrdersTab from './OrdersTab';
import * as api from './api';

vi.mock('./api');

describe('OrdersTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listOrders.mockResolvedValue([
      { order_id: 1, patient_name: 'Otieno, Sam', patient_id: 5, treatment_no: 3, status: 'Ordered' },
    ]);
    api.getOrder.mockResolvedValue({
      order_id: 1, patient_name: 'Otieno, Sam', patient_id: 5, treatment_no: 3, status: 'Ordered',
      observations: [], complications: [], adequacy: null, checklist_runs: [],
    });
  });

  it('lists sessions with a status chip and a New session button', async () => {
    render(<OrdersTab />);
    expect(await screen.findByText(/Otieno, Sam/)).toBeInTheDocument();
    expect(screen.getByText('Ordered', { selector: 'span' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /new session/i })).toBeInTheDocument();
  });

  it('opens a session board on row click', async () => {
    const user = userEvent.setup();
    render(<OrdersTab />);
    await user.click(await screen.findByText(/Otieno, Sam/));
    await waitFor(() => expect(api.getOrder).toHaveBeenCalledWith(1));
    expect(await screen.findByRole('region', { name: /session detail/i })).toBeInTheDocument();
  });

  it('reloads with a status filter', async () => {
    const user = userEvent.setup();
    render(<OrdersTab />);
    await screen.findByText(/Otieno, Sam/);
    await user.selectOptions(screen.getByRole('combobox'), 'Completed');
    await waitFor(() => expect(api.listOrders).toHaveBeenCalledWith({ status: 'Completed' }));
  });
});
