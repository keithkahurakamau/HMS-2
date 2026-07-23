import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import CaseBoard from './CaseBoard';
import * as api from './api';

vi.mock('./api');

const baseCase = (over = {}) => ({
  case_id: 1, patient_name: 'Otieno, Sam', patient_id: 5, procedure_name: 'Appendectomy',
  status: 'Scheduled', checklist_runs: [], operative_note: null, anaesthesia: null,
  team_members: [], consumables: [], recovery_observations: [], ...over,
});

describe('CaseBoard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listChecklists.mockResolvedValue([
      { checklist_id: 1, phase: 'TimeOut', name: 'Confirm patient, site, procedure', is_active: true },
    ]);
  });

  it('disables Start until WHO Time-Out is signed', async () => {
    render(<CaseBoard caseObj={baseCase()} onChanged={() => {}} />);
    expect(await screen.findByRole('button', { name: /start surgery/i })).toBeDisabled();
  });

  it('enables Start once a Time-Out run is checked', async () => {
    render(<CaseBoard caseObj={baseCase({ checklist_runs: [{ run_id: 1, phase: 'TimeOut', checked: true }] })} onChanged={() => {}} />);
    expect(await screen.findByRole('button', { name: /start surgery/i })).toBeEnabled();
  });

  it('starts the case and refreshes', async () => {
    api.startCase.mockResolvedValue({});
    api.getCase.mockResolvedValue(baseCase({ status: 'InTheatre', checklist_runs: [{ run_id: 1, phase: 'TimeOut', checked: true }] }));
    const onChanged = vi.fn();
    const user = userEvent.setup();
    render(<CaseBoard caseObj={baseCase({ checklist_runs: [{ run_id: 1, phase: 'TimeOut', checked: true }] })} onChanged={onChanged} />);
    await user.click(await screen.findByRole('button', { name: /start surgery/i }));
    await waitFor(() => expect(api.startCase).toHaveBeenCalledWith(1));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(expect.objectContaining({ status: 'InTheatre' })));
  });
});
