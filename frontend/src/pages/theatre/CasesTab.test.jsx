import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import CasesTab from './CasesTab';
import * as api from './api';

vi.mock('./api');

describe('CasesTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listCases.mockResolvedValue([
      { case_id: 1, patient_name: 'Otieno, Sam', patient_id: 5, procedure_name: 'Appendectomy', status: 'Scheduled' },
    ]);
    api.listChecklists.mockResolvedValue([]);
    api.getCase.mockResolvedValue({
      case_id: 1, patient_name: 'Otieno, Sam', patient_id: 5, procedure_name: 'Appendectomy', status: 'Scheduled',
      checklist_runs: [], operative_note: null, anaesthesia: null, team_members: [], consumables: [], recovery_observations: [],
    });
  });

  it('lists cases with a status chip and a New case button', async () => {
    render(<CasesTab />);
    expect(await screen.findByText(/Otieno, Sam/)).toBeInTheDocument();
    expect(screen.getByText('Scheduled', { selector: 'span' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /new case/i })).toBeInTheDocument();
  });

  it('opens a case board on row click', async () => {
    const user = userEvent.setup();
    render(<CasesTab />);
    await user.click(await screen.findByText(/Otieno, Sam/));
    await waitFor(() => expect(api.getCase).toHaveBeenCalledWith(1));
    expect(await screen.findByRole('region', { name: /case detail/i })).toBeInTheDocument();
  });

  it('reloads with a status filter', async () => {
    const user = userEvent.setup();
    render(<CasesTab />);
    await screen.findByText(/Otieno, Sam/);
    await user.selectOptions(screen.getByRole('combobox'), 'Completed');
    await waitFor(() => expect(api.listCases).toHaveBeenCalledWith({ status: 'Completed' }));
  });
});
