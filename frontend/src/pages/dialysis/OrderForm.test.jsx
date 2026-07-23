import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import OrderForm from './OrderForm';
import * as api from './api';

vi.mock('./api');

describe('OrderForm', () => {
  it('renders grouped prescription cards', () => {
    render(<OrderForm onClose={() => {}} onSaved={() => {}} />);
    expect(screen.getByText(/renal prescription/i)).toBeInTheDocument();
    expect(screen.getByText(/anticoagulation/i)).toBeInTheDocument();
    expect(screen.getByText(/fluid targets/i)).toBeInTheDocument();
  });

  it('requires a patient id', async () => {
    const user = userEvent.setup();
    render(<OrderForm onClose={() => {}} onSaved={() => {}} />);
    await user.click(screen.getByRole('button', { name: /create session/i }));
    expect(screen.getByText(/patient id is required/i)).toBeInTheDocument();
    expect(api.createOrder).not.toHaveBeenCalled();
  });

  it('submits an assembled payload', async () => {
    api.createOrder.mockResolvedValue({ order_id: 9 });
    const onSaved = vi.fn();
    const user = userEvent.setup();
    render(<OrderForm onClose={() => {}} onSaved={onSaved} />);
    await user.type(screen.getByLabelText(/patient id/i), '5');
    await user.type(screen.getByLabelText(/^dialyzer$/i), 'F6');
    await user.click(screen.getByRole('button', { name: /create session/i }));
    await waitFor(() => expect(api.createOrder).toHaveBeenCalledWith(
      expect.objectContaining({ patient_id: 5, dialyzer: 'F6' })));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
  });
});
