import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import AssessPlanModal from './AssessPlanModal';

describe('AssessPlanModal', () => {
    it('parses the incoming value into the two fields and saves serialized', async () => {
        const onSave = vi.fn();
        const user = userEvent.setup();
        render(<AssessPlanModal value={'Assessment:\nStable\n\nPlan:\nReview'} onSave={onSave} onClose={() => {}} />);

        expect(screen.getByLabelText(/^assessment$/i)).toHaveValue('Stable');
        expect(screen.getByLabelText(/^plan$/i)).toHaveValue('Review');
        await user.click(screen.getByRole('button', { name: /^save$/i }));
        expect(onSave).toHaveBeenCalledWith('Assessment:\nStable\n\nPlan:\nReview');
    });
});
