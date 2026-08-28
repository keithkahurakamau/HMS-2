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
    it('never grows past the top of the viewport when it flips upward', async () => {
        // A trigger low on a short screen: there is no room below, so the menu
        // flips up. The panel must then fit the space ABOVE the trigger, not a
        // flat 70vh, or its first items get sliced off at the viewport edge.
        const user = userEvent.setup();
        vi.spyOn(window, 'innerHeight', 'get').mockReturnValue(760);
        vi.spyOn(window, 'innerWidth', 'get').mockReturnValue(1440);
        const rect = { top: 520, bottom: 552, left: 1200, right: 1330, width: 130, height: 32 };
        vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect')
            .mockReturnValue({ ...rect, x: rect.left, y: rect.top, toJSON: () => rect });

        render(<ActionsMenu groups={groups} has={() => true} />);
        await user.click(screen.getByRole('button', { name: /actions/i }));

        const menu = screen.getByRole('menu');
        // Space above the trigger is 520px, minus the 10px offset and an 8px
        // margin, so the panel may be at most 502px tall.
        const maxHeight = parseInt(menu.style.maxHeight, 10);
        expect(maxHeight).toBeGreaterThan(0);
        expect(maxHeight).toBeLessThanOrEqual(502);
        vi.restoreAllMocks();
    });


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
