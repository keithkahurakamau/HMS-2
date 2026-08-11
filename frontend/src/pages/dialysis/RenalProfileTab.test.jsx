import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import RenalProfileTab from './RenalProfileTab';
import * as api from './api';

vi.mock('./api');

describe('RenalProfileTab', () => {
  it('loads and displays a patient renal profile', async () => {
    api.getRenalProfile.mockResolvedValue({
      patient_id: 5, patient_name: 'Otieno, Sam',
      accesses: [{ access_id: 1, type: 'AVF', site: 'Left radiocephalic', status: 'Active' }],
      schedule: { pattern: 'MWF', shift: 'Morning', target_dry_weight_kg: 70 },
      adequacy_trend: [{ order_id: 3, urr: 70, kt_v: 1.42 }],
    });
    const user = userEvent.setup();
    render(<RenalProfileTab />);
    await user.type(screen.getByLabelText(/patient id/i), '5');
    await user.click(screen.getByRole('button', { name: /load profile/i }));
    await waitFor(() => expect(api.getRenalProfile).toHaveBeenCalledWith('5'));
    expect(await screen.findByText('Otieno, Sam')).toBeInTheDocument();
    expect(screen.getByText(/Left radiocephalic/)).toBeInTheDocument();
    expect(screen.getByText('1.42')).toBeInTheDocument();
  });
});
