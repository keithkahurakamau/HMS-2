import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../../api/client', () => ({ apiClient: { get: vi.fn() } }));

import { apiClient } from '../../api/client';
import SuperAdminDashboard from './SuperAdminDashboard';

/**
 * Task 10: the Global Overview's MRR tile is a price-list projection, the
 * same number whether every hospital has paid or none of them have.
 * collected_this_month is the real cash-in figure shown beside it, and the
 * tile's label must say "projected" so the two can never be confused.
 */
const overview = {
    tenants: { total: 5, active: 4, suspended: 1, premium: 2, standard: 2 },
    users: { total_active: 120, errors: [] },
    revenue: { mrr: 136000, arr: 1632000, collected_this_month: '54321.00', currency: 'KES' },
    growth: { window_days: 30, new_tenants: 1, percent: 20 },
    tickets: { open: 0, in_progress: 0 },
    recent_tenants: [],
};

describe('SuperAdminDashboard', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        apiClient.get.mockResolvedValue({ data: overview });
    });

    it('shows collected-this-month beside the MRR tile, with the MRR tile labelled as a projection', async () => {
        render(<MemoryRouter><SuperAdminDashboard /></MemoryRouter>);

        // The MRR value itself is unchanged.
        expect(await screen.findByText('KES 136,000')).toBeInTheDocument();
        // The tile's label makes it explicit this is a projection.
        expect(screen.getByText('Monthly recurring revenue (projected)')).toBeInTheDocument();
        // The real cash-in figure, formatted from the decimal string, sits
        // beside it.
        expect(screen.getByText(/KES 54,321\.00 collected this month/)).toBeInTheDocument();
    });
});
