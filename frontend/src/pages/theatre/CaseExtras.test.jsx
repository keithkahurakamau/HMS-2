import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { within } from '@testing-library/react';
import CaseExtras from './CaseExtras';
import * as api from './api';

vi.mock('./api');

const baseCase = (over = {}) => ({
  case_id: 1, status: 'InTheatre', team_members: [], consumables: [], recovery_observations: [], ...over,
});

describe('CaseExtras', () => {
  it('renders team, implants and recovery obs from the case', () => {
    render(<CaseExtras onChanged={() => {}} caseObj={baseCase({
      status: 'Recovery',
      team_members: [{ member_id: 1, name: 'Dr A', role: 'Surgeon' }],
      consumables: [{ consumable_id: 1, item_name: 'Hip prosthesis', is_implant: true, serial_no: 'IMP-77' }],
      recovery_observations: [{ obs_id: 1, pulse: 78, spo2: 98, recorded_at: '2026-07-23T10:00:00Z' }],
    })} />);
    expect(screen.getByText(/Dr A/)).toBeInTheDocument();
    expect(screen.getByText(/Hip prosthesis/)).toBeInTheDocument();
    expect(screen.getByText('78')).toBeInTheDocument();
  });

  it('adds a team member', async () => {
    api.addTeamMember.mockResolvedValue({ member_id: 2 });
    api.getCase.mockResolvedValue(baseCase({ team_members: [{ member_id: 2, name: 'Dr B', role: 'Assistant' }] }));
    const onChanged = vi.fn();
    const user = userEvent.setup();
    render(<CaseExtras caseObj={baseCase()} onChanged={onChanged} />);
    const teamSection = screen.getByRole('region', { name: /surgical team/i });
    await user.type(within(teamSection).getByLabelText(/name/i), 'Dr B');
    await user.click(within(teamSection).getByRole('button', { name: /add/i }));
    await waitFor(() => expect(api.addTeamMember).toHaveBeenCalledWith(1, expect.objectContaining({ role: 'Surgeon', name: 'Dr B' })));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });
});
