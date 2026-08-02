import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { Pill } from 'lucide-react';
import ActionsMenu from './ActionsMenu';

const groups = [
    { label: 'Clinical', items: [
        { label: 'Prescription', icon: Pill, onClick: vi.fn(), perm: 'clinical:write' },
        { label: 'View only', onClick: vi.fn() },
    ] },
    { label: 'Flow', items: [
        { label: 'Add to queue', onClick: vi.fn(), perm: 'patients:write' },
    ] },
];

describe('ActionsMenu', () => {
    it('opens and hides items the user lacks permission for', async () => {
        const has = (p) => p === 'clinical:write'; // no patients:write
        const user = userEvent.setup();
        render(<ActionsMenu groups={groups} has={has} />);
        await user.click(screen.getByRole('button', { name: /actions/i }));

        expect(screen.getByRole('menuitem', { name: /prescription/i })).toBeInTheDocument();
        expect(screen.getByRole('menuitem', { name: /view only/i })).toBeInTheDocument();
        // Flow group's only item needs patients:write → whole group hidden
        expect(screen.queryByText('Flow')).not.toBeInTheDocument();
        expect(screen.queryByRole('menuitem', { name: /add to queue/i })).not.toBeInTheDocument();
    });

    it('fires the item handler and closes', async () => {
        const onClick = vi.fn();
        const g = [{ label: 'Clinical', items: [{ label: 'Vitals', onClick }] }];
        const user = userEvent.setup();
        render(<ActionsMenu groups={g} has={() => true} />);
        await user.click(screen.getByRole('button', { name: /actions/i }));
        await user.click(screen.getByRole('menuitem', { name: /vitals/i }));
        expect(onClick).toHaveBeenCalled();
        expect(screen.queryByRole('menuitem', { name: /vitals/i })).not.toBeInTheDocument();
    });

    it('renders nothing when no group has visible items', () => {
        const g = [{ label: 'Clinical', items: [{ label: 'X', onClick: vi.fn(), perm: 'nope' }] }];
        const { container } = render(<ActionsMenu groups={g} has={() => false} />);
        expect(container).toBeEmptyDOMElement();
    });
});
