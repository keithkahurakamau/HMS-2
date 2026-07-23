import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import CaseForm from './CaseForm';
import * as api from './api';

vi.mock('./api');

describe('CaseForm', () => {
  it('requires patient id and procedure', async () => {
    const user = userEvent.setup();
    render(<CaseForm onClose={() => {}} onSaved={() => {}} />);
    await user.click(screen.getByRole('button', { name: /create case/i }));
    expect(screen.getByText(/patient id is required/i)).toBeInTheDocument();
    expect(api.createCase).not.toHaveBeenCalled();
  });

  it('submits an assembled payload', async () => {
    api.createCase.mockResolvedValue({ case_id: 9 });
    const onSaved = vi.fn();
    const user = userEvent.setup();
    render(<CaseForm onClose={() => {}} onSaved={onSaved} />);
    await user.type(screen.getByLabelText(/patient id/i), '5');
    await user.type(screen.getByLabelText(/^procedure \*$/i), 'Appendectomy');
    await user.click(screen.getByRole('button', { name: /create case/i }));
    await waitFor(() => expect(api.createCase).toHaveBeenCalledWith(
      expect.objectContaining({ patient_id: 5, procedure_name: 'Appendectomy', priority: 'Elective' })));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
  });
});
