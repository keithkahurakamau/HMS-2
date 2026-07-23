import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import MachinesTab from './MachinesTab';
import * as api from './api';

vi.mock('./api');

describe('MachinesTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listMachines.mockResolvedValue([
      { machine_id: 1, name: 'HD-01', model: 'Fresenius 4008S', station: 'Station 1', is_active: true },
    ]);
  });

  it('lists machines with an active chip', async () => {
    render(<MachinesTab />);
    expect(await screen.findByText('HD-01')).toBeInTheDocument();
    expect(screen.getByText('Active')).toBeInTheDocument();
  });

  it('adds a machine', async () => {
    api.createMachine.mockResolvedValue({ machine_id: 2 });
    const user = userEvent.setup();
    render(<MachinesTab />);
    await screen.findByText('HD-01');
    await user.type(screen.getByLabelText(/^name$/i), 'HD-02');
    await user.click(screen.getByRole('button', { name: /add machine/i }));
    await waitFor(() => expect(api.createMachine).toHaveBeenCalledWith(expect.objectContaining({ name: 'HD-02' })));
  });
});
