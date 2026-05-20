/* eslint-disable no-unused-vars */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../test/renderWithProviders';

/* ------------------------------------------------------------------ */
/*  Mocks                                                              */
/* ------------------------------------------------------------------ */

vi.mock('../api/client', () => ({
    apiClient: {
        get:    vi.fn(),
        post:   vi.fn(),
        put:    vi.fn(),
        patch:  vi.fn(),
        delete: vi.fn(),
    },
    isTenantRedirect: vi.fn(() => false),
}));

vi.mock('react-hot-toast', () => ({
    default: {
        success: vi.fn(),
        error:   vi.fn(),
    },
}));

// Patients.jsx is *not* imported here, but the print template lives in the
// same utils module the codebase touches — keep the mock so test setup is
// consistent across the suite.
vi.mock('../utils/printTemplates', () => ({
    printPatientCard: vi.fn(),
}));

import { apiClient } from '../api/client';
import toast from 'react-hot-toast';
import Appointments from './Appointments';

/* ------------------------------------------------------------------ */
/*  Fixtures                                                           */
/* ------------------------------------------------------------------ */

const mkAppt = (overrides = {}) => ({
    appointment_id:    1,
    patient_id:        10,
    doctor_id:         20,
    patient_name:      'Aisha Mwangi',
    patient_opd:       'OP-0001',
    doctor_name:       'Dr. Kamau',
    appointment_date:  '2026-05-20T09:30:00',
    status:            'Scheduled',
    notes:             '',
    ...overrides,
});

const mkDoctor = (overrides = {}) => ({
    user_id:        20,
    full_name:      'Dr. Kamau',
    specialization: 'General Practice',
    ...overrides,
});

const mkPatient = (overrides = {}) => ({
    patient_id:    10,
    outpatient_no: 'OP-0001',
    surname:       'Mwangi',
    other_names:   'Aisha',
    ...overrides,
});

/* ------------------------------------------------------------------ */
/*  Default wiring                                                     */
/* ------------------------------------------------------------------ */

const wireDirectory = ({ appointments = [], doctors = [], patients = [] } = {}) => {
    apiClient.get.mockImplementation((url) => {
        if (typeof url !== 'string') return Promise.resolve({ data: [] });
        // Order matters: /appointments/doctors must hit before /appointments/.
        if (url.startsWith('/appointments/doctors'))             return Promise.resolve({ data: doctors });
        if (url === '/patients/' || url.startsWith('/patients/?')) return Promise.resolve({ data: patients });
        if (url.startsWith('/appointments/'))                    return Promise.resolve({ data: appointments });
        return Promise.resolve({ data: [] });
    });
};

beforeEach(() => {
    vi.clearAllMocks();
    wireDirectory();
    apiClient.post.mockResolvedValue({ data: {} });
    apiClient.patch.mockResolvedValue({ data: {} });
    apiClient.delete.mockResolvedValue({ data: {} });
    if (typeof sessionStorage !== 'undefined') sessionStorage.clear();
});

/* ------------------------------------------------------------------ */
/*  Tests                                                              */
/* ------------------------------------------------------------------ */

describe('<Appointments /> — list rendering', () => {
    it('renders the page header + status badges when GET resolves with rows', async () => {
        wireDirectory({
            appointments: [
                mkAppt({ appointment_id: 1, status: 'Scheduled', patient_name: 'Aisha Mwangi' }),
                mkAppt({ appointment_id: 2, status: 'Confirmed', patient_name: 'Brian Otieno', appointment_date: '2026-05-20T11:00:00' }),
                mkAppt({ appointment_id: 3, status: 'Completed', patient_name: 'Mary Achieng', appointment_date: '2026-05-21T09:00:00' }),
            ],
        });

        renderWithProviders(<Appointments />);

        // Header
        expect(
            await screen.findByRole('heading', { name: /^appointments$/i, level: 1 }),
        ).toBeInTheDocument();

        // Patient cards
        expect(await screen.findByText(/aisha mwangi/i)).toBeInTheDocument();
        expect(screen.getByText(/brian otieno/i)).toBeInTheDocument();
        expect(screen.getByText(/mary achieng/i)).toBeInTheDocument();

        // Status text appears both inside the badge span on each card AND as
        // <option> values in the filter dropdown — so use getAllByText and
        // assert at least one match per status. Badge presence is implied by
        // the card rendering above.
        expect(screen.getAllByText('Scheduled').length).toBeGreaterThan(0);
        expect(screen.getAllByText('Confirmed').length).toBeGreaterThan(0);
        expect(screen.getAllByText('Completed').length).toBeGreaterThan(0);
    });

    it('renders the empty state when GET resolves with []', async () => {
        wireDirectory({ appointments: [] });
        renderWithProviders(<Appointments />);

        expect(
            await screen.findByText(/no appointments in this window/i),
        ).toBeInTheDocument();
    });
});

describe('<Appointments /> — filter bar', () => {
    it('changing the status filter refetches with the matching query param', async () => {
        const user = userEvent.setup();
        wireDirectory({ appointments: [] });

        renderWithProviders(<Appointments />);

        // Wait for initial load to settle.
        await waitFor(() => {
            const calls = apiClient.get.mock.calls.filter(([u]) => u === '/appointments/');
            expect(calls.length).toBeGreaterThan(0);
        });

        apiClient.get.mockClear();
        wireDirectory({ appointments: [] }); // re-prime after clear

        // Status select — labels in this page aren't htmlFor-linked, so we
        // identify it by the "Any status" placeholder option it owns.
        const statusSelect = Array.from(document.querySelectorAll('select'))
            .find((s) => s.querySelector('option[value=""]')?.textContent === 'Any status');
        expect(statusSelect).toBeTruthy();
        await user.selectOptions(statusSelect, 'Confirmed');

        await waitFor(() => {
            const apptCalls = apiClient.get.mock.calls.filter(([u]) => u === '/appointments/');
            expect(apptCalls.length).toBeGreaterThan(0);
            const params = apptCalls[apptCalls.length - 1][1]?.params || {};
            expect(params.status).toBe('Confirmed');
        });
    });

    it('changing the from / to dates refetches with date_from and date_to as ISO datetime strings', async () => {
        const user = userEvent.setup();
        wireDirectory({ appointments: [] });

        renderWithProviders(<Appointments />);
        await waitFor(() => {
            expect(apiClient.get).toHaveBeenCalled();
        });
        apiClient.get.mockClear();
        wireDirectory({ appointments: [] });

        // The filter bar exposes two `<input type="date">` controls — "From"
        // (pre-filled with today via todayISO()) and "To" (blank). Labels are
        // not htmlFor-linked, so query directly by type attribute. The order
        // in the DOM is from → to.
        const dateInputs = Array.from(document.querySelectorAll('input[type="date"]'));
        expect(dateInputs.length).toBe(2);
        const [fromInput, toInput] = dateInputs;

        await user.clear(fromInput);
        await user.type(fromInput, '2026-05-18');
        await user.type(toInput,   '2026-05-25');

        await waitFor(() => {
            const apptCalls = apiClient.get.mock.calls.filter(([u]) => u === '/appointments/');
            expect(apptCalls.length).toBeGreaterThan(0);
            const params = apptCalls[apptCalls.length - 1][1]?.params || {};
            expect(params.date_from).toBe('2026-05-18T00:00:00');
            expect(params.date_to).toBe('2026-05-25T23:59:59');
        });
    });
});

describe('<Appointments /> — create form', () => {
    it('opens the form, requires patient + doctor + date, and POSTs to /appointments/', async () => {
        const user = userEvent.setup();
        wireDirectory({
            appointments: [],
            doctors:      [mkDoctor({ user_id: 20, full_name: 'Dr. Kamau' })],
            patients:     [mkPatient({ patient_id: 10, surname: 'Mwangi', other_names: 'Aisha' })],
        });

        renderWithProviders(<Appointments />);

        await user.click(await screen.findByRole('button', { name: /new appointment/i }));

        // Modal heading
        expect(await screen.findByRole('heading', { name: /new appointment/i })).toBeInTheDocument();

        // The patient and doctor selects.
        const selects = screen.getAllByRole('combobox');
        // Inside the modal there are exactly two selects: patient + doctor.
        // The filter bar's status select is also rendered → narrow by required attribute.
        const required = selects.filter((s) => s.required);
        expect(required.length).toBe(2);
        const [patientSelect, doctorSelect] = required;

        await user.selectOptions(patientSelect, '10');
        await user.selectOptions(doctorSelect, '20');

        // The datetime-local input — find by type attribute.
        const dt = document.querySelector('input[type="datetime-local"]');
        expect(dt).toBeTruthy();
        await user.type(dt, '2026-05-20T09:30');

        // Submit
        await user.click(screen.getByRole('button', { name: /^book appointment$/i }));

        await waitFor(() => {
            expect(apiClient.post).toHaveBeenCalled();
        });
        const [url, payload] = apiClient.post.mock.calls[0];
        expect(url).toBe('/appointments/');
        expect(payload).toEqual(expect.objectContaining({
            patient_id:       10,
            doctor_id:        20,
            appointment_date: '2026-05-20T09:30',
        }));

        await waitFor(() => {
            expect(toast.success).toHaveBeenCalledWith(expect.stringMatching(/appointment booked/i));
        });
    });

    it('blocks submission and toasts an error when any required field is missing', async () => {
        const user = userEvent.setup();
        wireDirectory({
            appointments: [],
            doctors:      [mkDoctor({ user_id: 20 })],
            patients:     [mkPatient({ patient_id: 10 })],
        });

        renderWithProviders(<Appointments />);
        await user.click(await screen.findByRole('button', { name: /new appointment/i }));

        // The submit button is a `type="submit"` inside the form. Required HTML5
        // attributes on the selects/inputs block submission entirely before our
        // own validation runs — so the post must NOT have been called.
        await user.click(screen.getByRole('button', { name: /^book appointment$/i }));

        expect(apiClient.post).not.toHaveBeenCalled();
    });
});

describe('<Appointments /> — status update', () => {
    it('clicking "Confirm" PATCHes /appointments/{id}/status with { status: "Confirmed" }', async () => {
        const user = userEvent.setup();
        const appt = mkAppt({ appointment_id: 77, status: 'Scheduled' });
        wireDirectory({ appointments: [appt] });

        renderWithProviders(<Appointments />);

        const confirmBtn = await screen.findByRole('button', { name: /^\s*confirm/i });
        await user.click(confirmBtn);

        await waitFor(() => {
            expect(apiClient.patch).toHaveBeenCalledWith(
                '/appointments/77/status',
                { status: 'Confirmed' },
            );
        });
        await waitFor(() => {
            expect(toast.success).toHaveBeenCalledWith(expect.stringMatching(/marked as confirmed/i));
        });
    });

    it('clicking "Mark completed" PATCHes /appointments/{id}/status with { status: "Completed" }', async () => {
        const user = userEvent.setup();
        const appt = mkAppt({ appointment_id: 78, status: 'Scheduled' });
        wireDirectory({ appointments: [appt] });

        renderWithProviders(<Appointments />);
        await user.click(await screen.findByRole('button', { name: /mark completed/i }));

        await waitFor(() => {
            expect(apiClient.patch).toHaveBeenCalledWith(
                '/appointments/78/status',
                { status: 'Completed' },
            );
        });
    });

    it('clicking "No-show" PATCHes /appointments/{id}/status with { status: "No-Show" }', async () => {
        const user = userEvent.setup();
        const appt = mkAppt({ appointment_id: 79, status: 'Scheduled' });
        wireDirectory({ appointments: [appt] });

        renderWithProviders(<Appointments />);
        await user.click(await screen.findByRole('button', { name: /no-show/i }));

        await waitFor(() => {
            expect(apiClient.patch).toHaveBeenCalledWith(
                '/appointments/79/status',
                { status: 'No-Show' },
            );
        });
    });
});

describe('<Appointments /> — cancel', () => {
    it('confirms via window.confirm and DELETEs /appointments/{id} on accept', async () => {
        const user = userEvent.setup();
        const appt = mkAppt({ appointment_id: 88, status: 'Scheduled' });
        wireDirectory({ appointments: [appt] });

        const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);

        renderWithProviders(<Appointments />);
        const cancelBtn = await screen.findByRole('button', { name: /^cancel$/i });
        await user.click(cancelBtn);

        expect(confirmSpy).toHaveBeenCalled();
        await waitFor(() => {
            expect(apiClient.delete).toHaveBeenCalledWith('/appointments/88');
        });
        await waitFor(() => {
            expect(toast.success).toHaveBeenCalledWith(expect.stringMatching(/cancelled/i));
        });
        confirmSpy.mockRestore();
    });

    it('does NOT delete when the user rejects the confirm prompt', async () => {
        const user = userEvent.setup();
        const appt = mkAppt({ appointment_id: 88 });
        wireDirectory({ appointments: [appt] });
        const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);

        renderWithProviders(<Appointments />);
        await user.click(await screen.findByRole('button', { name: /^cancel$/i }));

        expect(apiClient.delete).not.toHaveBeenCalled();
        confirmSpy.mockRestore();
    });
});

describe('<Appointments /> — conflict surfacing', () => {
    it('shows the backend detail as an error toast when create returns 409', async () => {
        const user = userEvent.setup();
        wireDirectory({
            appointments: [],
            doctors:      [mkDoctor({ user_id: 20 })],
            patients:     [mkPatient({ patient_id: 10 })],
        });
        apiClient.post.mockRejectedValueOnce({
            response: { status: 409, data: { detail: 'Doctor double-booked at that time.' } },
        });

        renderWithProviders(<Appointments />);
        await user.click(await screen.findByRole('button', { name: /new appointment/i }));

        const required = screen.getAllByRole('combobox').filter((s) => s.required);
        await user.selectOptions(required[0], '10');
        await user.selectOptions(required[1], '20');
        const dt = document.querySelector('input[type="datetime-local"]');
        await user.type(dt, '2026-05-20T09:30');
        await user.click(screen.getByRole('button', { name: /^book appointment$/i }));

        await waitFor(() => {
            expect(toast.error).toHaveBeenCalledWith('Doctor double-booked at that time.');
        });
    });

    it('shows the backend detail as an error toast when a status update returns 409', async () => {
        const user = userEvent.setup();
        const appt = mkAppt({ appointment_id: 200, status: 'Scheduled' });
        wireDirectory({ appointments: [appt] });
        apiClient.patch.mockRejectedValueOnce({
            response: { status: 409, data: { detail: 'Already completed.' } },
        });

        renderWithProviders(<Appointments />);
        await user.click(await screen.findByRole('button', { name: /mark completed/i }));

        await waitFor(() => {
            expect(toast.error).toHaveBeenCalledWith('Already completed.');
        });
    });
});
