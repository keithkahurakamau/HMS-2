import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import PatientSearch from './PatientSearch';
import { apiClient } from '../api/client';

vi.mock('../api/client', () => ({ apiClient: { get: vi.fn() } }));

describe('PatientSearch', () => {
  beforeEach(() => vi.clearAllMocks());

  it('searches by name and returns the picked patient', async () => {
    apiClient.get.mockResolvedValue({
      data: [{ patient_id: 7, surname: 'Otieno', other_names: 'Sam', outpatient_no: 'OP-100', sex: 'Male' }],
    });
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(<PatientSearch onSelect={onSelect} />);

    await user.type(screen.getByRole('combobox'), 'Sam');
    await waitFor(() => expect(apiClient.get).toHaveBeenCalledWith(
      '/patients/', expect.objectContaining({ params: expect.objectContaining({ search: 'Sam' }) })));

    await user.click(await screen.findByText(/Otieno, Sam/));
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ patient_id: 7 }));
  });

  it('does not search for queries shorter than 2 chars', async () => {
    const user = userEvent.setup();
    render(<PatientSearch onSelect={() => {}} />);
    await user.type(screen.getByRole('combobox'), 'S');
    // give the debounce a chance
    await new Promise((r) => setTimeout(r, 300));
    expect(apiClient.get).not.toHaveBeenCalled();
  });
});
