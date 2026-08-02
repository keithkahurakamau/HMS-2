import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import PrescriptionModal from './PrescriptionModal';

describe('PrescriptionModal', () => {
    it('saves only rows with a drug name', async () => {
        const onSave = vi.fn();
        const user = userEvent.setup();
        render(<PrescriptionModal medications={[]} onSave={onSave} onClose={() => {}} />);

        await user.click(screen.getByRole('button', { name: /add medication/i })); // now 2 empty rows
        const drugInputs = screen.getAllByLabelText(/^drug$/i);
        await user.type(drugInputs[0], 'Amoxicillin');
        await user.click(screen.getByRole('button', { name: /save prescription/i }));

        expect(onSave).toHaveBeenCalledWith([expect.objectContaining({ drug: 'Amoxicillin' })]);
    });

    it('pre-fills existing medications', () => {
        render(<PrescriptionModal medications={[{ drug: 'Metformin', formulation: 'Tablet', dosage: '500 mg', frequency: '', duration: '' }]}
            onSave={() => {}} onClose={() => {}} />);
        expect(screen.getByDisplayValue('Metformin')).toBeInTheDocument();
    });
});
