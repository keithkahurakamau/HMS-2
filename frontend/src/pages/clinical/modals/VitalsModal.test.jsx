import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import VitalsModal from './VitalsModal';

describe('VitalsModal', () => {
    it('shows a live BMI readout and saves the edited copy', async () => {
        const onSave = vi.fn();
        const user = userEvent.setup();
        render(<VitalsModal vitals={{ weight: '70', height: '170' }} onSave={onSave} onClose={() => {}} />);

        expect(screen.getByText('24.2')).toBeInTheDocument();
        await user.type(screen.getByLabelText(/blood pressure/i), '120/80');
        await user.click(screen.getByRole('button', { name: /save vitals/i }));

        expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ weight: '70', bp: '120/80' }));
    });
});
