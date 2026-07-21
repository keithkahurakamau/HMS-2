import React, { useState } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../api/client', () => ({
    apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
    isTenantRedirect: vi.fn(() => false),
}));

import { apiClient } from '../api/client';
import IcdDiagnosisPicker from './IcdDiagnosisPicker';

const RESULTS = [
    { code: 'E11.9', description: 'Type 2 diabetes mellitus without complications' },
    { code: 'E11.2', description: 'Type 2 diabetes mellitus with kidney complications' },
];

function Harness({ initial = [] }) {
    const [codes, setCodes] = useState(initial);
    return <IcdDiagnosisPicker codes={codes} onChange={setCodes} />;
}

beforeEach(() => {
    vi.clearAllMocks();
    apiClient.get.mockResolvedValue({ data: RESULTS });
});

describe('IcdDiagnosisPicker', () => {
    it('adds a chip when a search result is picked, and clears the input', async () => {
        const user = userEvent.setup();
        render(<Harness />);
        const input = screen.getByLabelText(/diagnoses \(icd-10\)/i);
        await user.type(input, 'E11');
        await waitFor(() => expect(apiClient.get).toHaveBeenCalledWith(
            '/clinical/icd10/search', { params: { q: 'E11' } }));
        // Match the dropdown row by its description — /E11\.9/ alone would
        // also match a chip's "Remove diagnosis E11.9" button.
        await user.click(await screen.findByRole('option', { name: /without complications/i }));
        expect(screen.getByText('E11.9')).toBeInTheDocument();
        expect(screen.getByText(/primary/i)).toBeInTheDocument();
        expect(input).toHaveValue('');
    });

    it('marks only the first chip as primary and removes chips', async () => {
        const user = userEvent.setup();
        render(<Harness initial={[
            { code: 'E11.9', description: 'T2DM' },
            { code: 'I10', description: 'Hypertension' },
        ]} />);
        expect(screen.getAllByText(/primary/i)).toHaveLength(1);
        await user.click(screen.getByRole('button', { name: /remove diagnosis E11\.9/i }));
        expect(screen.queryByText('E11.9')).not.toBeInTheDocument();
        // I10 promoted to primary
        expect(screen.getByText(/primary/i)).toBeInTheDocument();
    });

    it('ignores duplicate codes', async () => {
        const user = userEvent.setup();
        render(<Harness initial={[{ code: 'E11.9', description: 'T2DM' }]} />);
        const input = screen.getByLabelText(/diagnoses \(icd-10\)/i);
        await user.type(input, 'E11');
        await user.click(await screen.findByRole('option', { name: /without complications/i }));
        expect(screen.getAllByText('E11.9')).toHaveLength(1);
    });

    it('blocks an 11th code with a hint', async () => {
        const user = userEvent.setup();
        const ten = Array.from({ length: 10 }, (_, i) => ({ code: `A0${i}`, description: `Dx ${i}` }));
        render(<Harness initial={ten} />);
        const input = screen.getByLabelText(/diagnoses \(icd-10\)/i);
        await user.type(input, 'E11');
        await user.click(await screen.findByRole('option', { name: /without complications/i }));
        expect(screen.queryByText('E11.9')).not.toBeInTheDocument();
        expect(screen.getByText(/maximum of 10/i)).toBeInTheDocument();
    });

    it('offers an "add as custom diagnosis" row alongside catalogue results', async () => {
        const user = userEvent.setup();
        render(<Harness />);
        await user.type(screen.getByLabelText(/diagnoses \(icd-10\)/i), 'E11');
        await screen.findByRole('option', { name: /without complications/i });
        expect(screen.getByRole('option', { name: /add "E11" as custom diagnosis/i })).toBeInTheDocument();
    });

    it('adds a custom chip with a Note badge when the catalogue has no match', async () => {
        const user = userEvent.setup();
        apiClient.get.mockResolvedValue({ data: [] });
        render(<Harness />);
        const input = screen.getByLabelText(/diagnoses \(icd-10\)/i);
        await user.type(input, 'birth trauma');
        await user.click(await screen.findByRole('option', { name: /add "birth trauma" as custom diagnosis/i }));
        expect(screen.getByText('birth trauma')).toBeInTheDocument();
        expect(screen.getByText(/note/i)).toBeInTheDocument();
        expect(screen.getByText(/primary/i)).toBeInTheDocument();
        expect(input).toHaveValue('');
    });

    it('dedupes custom entries case-insensitively', async () => {
        const user = userEvent.setup();
        apiClient.get.mockResolvedValue({ data: [] });
        render(<Harness initial={[{ code: null, description: 'Birth Trauma', custom: true }]} />);
        await user.type(screen.getByLabelText(/diagnoses \(icd-10\)/i), 'birth trauma');
        await user.click(await screen.findByRole('option', { name: /add "birth trauma" as custom diagnosis/i }));
        expect(screen.getAllByText(/birth trauma/i)).toHaveLength(1);
    });

    it('counts custom entries toward the 10-diagnosis limit', async () => {
        const user = userEvent.setup();
        apiClient.get.mockResolvedValue({ data: [] });
        const ten = Array.from({ length: 10 }, (_, i) => ({ code: `A0${i}`, description: `Dx ${i}` }));
        render(<Harness initial={ten} />);
        await user.type(screen.getByLabelText(/diagnoses \(icd-10\)/i), 'birth trauma');
        await user.click(await screen.findByRole('option', { name: /add "birth trauma" as custom diagnosis/i }));
        expect(screen.queryByText('birth trauma')).not.toBeInTheDocument();
        expect(screen.getByText(/maximum of 10/i)).toBeInTheDocument();
    });

    it('removes a custom chip without disturbing catalogue chips', async () => {
        const user = userEvent.setup();
        render(<Harness initial={[
            { code: 'E11.9', description: 'T2DM' },
            { code: null, description: 'birth trauma', custom: true },
        ]} />);
        await user.click(screen.getByRole('button', { name: /remove diagnosis birth trauma/i }));
        expect(screen.queryByText('birth trauma')).not.toBeInTheDocument();
        expect(screen.getByText('E11.9')).toBeInTheDocument();
    });

    it('closes the dropdown on Escape', async () => {
        const user = userEvent.setup();
        render(<Harness />);
        await user.type(screen.getByLabelText(/diagnoses \(icd-10\)/i), 'E11');
        await screen.findByRole('option', { name: /without complications/i });
        await user.keyboard('{Escape}');
        expect(screen.queryByRole('option', { name: /without complications/i })).not.toBeInTheDocument();
    });

    it('closes the dropdown when clicking outside', async () => {
        const user = userEvent.setup();
        render(<Harness />);
        await user.type(screen.getByLabelText(/diagnoses \(icd-10\)/i), 'E11');
        await screen.findByRole('option', { name: /without complications/i });
        await user.click(document.body);
        expect(screen.queryByRole('option', { name: /without complications/i })).not.toBeInTheDocument();
    });

    it('supports ArrowDown + Enter keyboard selection', async () => {
        const user = userEvent.setup();
        render(<Harness />);
        const input = screen.getByLabelText(/diagnoses \(icd-10\)/i);
        await user.type(input, 'E11');
        await screen.findByRole('option', { name: /without complications/i });
        await user.keyboard('{ArrowDown}{Enter}');
        // Assert the chip specifically — the dropdown row also contains "E11.9".
        expect(screen.getByRole('button', { name: /remove diagnosis E11\.9/i })).toBeInTheDocument();
    });

    it('adds the typed text as custom on Enter when nothing is highlighted', async () => {
        const user = userEvent.setup();
        apiClient.get.mockResolvedValue({ data: [] });
        render(<Harness />);
        const input = screen.getByLabelText(/diagnoses \(icd-10\)/i);
        await user.type(input, 'birth trauma');
        await screen.findByRole('option', { name: /add "birth trauma" as custom diagnosis/i });
        await user.keyboard('{Enter}');
        expect(screen.getByText('birth trauma')).toBeInTheDocument();
        expect(screen.getByText(/note/i)).toBeInTheDocument();
    });
});
