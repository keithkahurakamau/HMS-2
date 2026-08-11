import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import AdequacyPanel from './AdequacyPanel';
import * as api from './api';

vi.mock('./api');

describe('AdequacyPanel', () => {
  it('shows existing adequacy metrics', () => {
    render(<AdequacyPanel order={{ order_id: 1, adequacy: { urr: 70.0, kt_v: 1.42 } }} />);
    expect(screen.getByText('70')).toBeInTheDocument();
    expect(screen.getByText('1.42')).toBeInTheDocument();
  });

  it('computes and displays URR + Kt/V on submit', async () => {
    api.recordAdequacy.mockResolvedValue({ urr: 65.0, kt_v: 1.3 });
    const user = userEvent.setup();
    render(<AdequacyPanel order={{ order_id: 1, adequacy: null }} />);
    await user.type(screen.getByLabelText(/pre-urea/i), '30');
    await user.type(screen.getByLabelText(/post-urea/i), '9');
    await user.type(screen.getByLabelText(/duration/i), '240');
    await user.type(screen.getByLabelText(/actual uf/i), '2500');
    await user.type(screen.getByLabelText(/post-weight/i), '70');
    await user.click(screen.getByRole('button', { name: /compute adequacy/i }));
    await waitFor(() => expect(api.recordAdequacy).toHaveBeenCalledWith(1,
      expect.objectContaining({ pre_urea: 30, post_urea: 9, session_duration_min: 240 })));
    expect(await screen.findByText('65')).toBeInTheDocument();
  });
});
