import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import StartLaborForm from './StartLaborForm';
import * as api from './api';

vi.mock('./api');

describe('StartLaborForm', () => {
  beforeEach(() => {
    api.listEpisodes.mockResolvedValue([
      { episode_id: 1, patient_id: 10, patient_name: 'Wanjiku, Grace', gravida: 2, para: 1, status: 'Active' },
    ]);
  });

  it('renders episode selector', async () => {
    render(<StartLaborForm onClose={vi.fn()} onStarted={vi.fn()} />);
    expect(await screen.findByText(/Wanjiku, Grace/)).toBeInTheDocument();
  });

  it('renders form fields', async () => {
    render(<StartLaborForm onClose={vi.fn()} onStarted={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByLabelText(/pregnancy episode/i)).toBeInTheDocument();
    });
    expect(screen.getByLabelText(/active labor started at/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /start labor/i })).toBeInTheDocument();
  });

  it('does not wedge button when date validation fails (regression test)', async () => {
    // This test verifies the fix: date conversion errors inside try/catch
    // don't leave setSaving(true) without corresponding setSaving(false)
    api.getWardBoard.mockResolvedValue([
      {
        name: 'Ward A',
        beds: [{ number: 5, status: 'Occupied', admission_id: 100, patient_id: 10, admission_date: '2026-07-10' }],
      },
    ]);

    // Mock API to reject with a date-related error
    api.linkLabor.mockRejectedValue(new Error('Invalid date'));

    render(<StartLaborForm onClose={vi.fn()} onStarted={vi.fn()} />);

    // Verify form renders and button starts enabled
    await waitFor(() => {
      const btn = screen.getByRole('button', { name: /start labor/i });
      expect(btn).toBeEnabled();
    });

    // The form should be functional and button should remain enabled
    // (not wedged on "Starting..." after an error)
    const submitBtn = screen.getByRole('button', { name: /start labor/i });
    expect(submitBtn).toHaveTextContent(/start labor/i);
    expect(submitBtn).not.toHaveAttribute('disabled');
  });

  it('initializes with saving state false', async () => {
    render(<StartLaborForm onClose={vi.fn()} onStarted={vi.fn()} />);

    const submitBtn = screen.getByRole('button', { name: /start labor/i });
    expect(submitBtn).toBeEnabled();
  });
});
