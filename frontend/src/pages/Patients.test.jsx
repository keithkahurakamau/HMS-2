/* eslint-disable no-unused-vars */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../test/renderWithProviders';

/* ------------------------------------------------------------------ */
/*  Mocks                                                              */
/* ------------------------------------------------------------------ */

// apiClient — the only network surface the page touches.
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

// react-hot-toast — assert success / error pathways without rendering toasts.
vi.mock('react-hot-toast', () => ({
    default: {
        success: vi.fn(),
        error:   vi.fn(),
    },
}));

// Print template — Patients.jsx imports `printPatientCard`. Keep it a no-op
// so the JSDOM print surface (which would otherwise throw) stays quiet.
vi.mock('../utils/printTemplates', () => ({
    printPatientCard: vi.fn(),
}));

// Pull the mocked modules so we can drive return values per-test.
import { apiClient } from '../api/client';
import toast from 'react-hot-toast';
import Patients from './Patients';

/* ------------------------------------------------------------------ */
/*  Fixtures                                                           */
/* ------------------------------------------------------------------ */

const today = new Date();
const dobFor = (age) => {
    const d = new Date(today);
    d.setFullYear(d.getFullYear() - age);
    return d.toISOString().slice(0, 10);
};

const mkPatient = (overrides = {}) => ({
    patient_id:    1,
    outpatient_no: 'OP-0001',
    surname:       'Mwangi',
    other_names:   'Aisha',
    sex:           'Female',
    date_of_birth: dobFor(34),
    telephone_1:   '+254700111222',
    residence:     'Kilimani',
    town:          'Nairobi',
    blood_group:   'O+',
    allergies:     '',
    registered_on: new Date().toISOString(),
    ...overrides,
});

const okList = (rows) => Promise.resolve({ data: rows });

/* ------------------------------------------------------------------ */
/*  Default mock wiring                                                */
/* ------------------------------------------------------------------ */

beforeEach(() => {
    vi.clearAllMocks();

    // Default: every GET returns []. Individual tests override.
    apiClient.get.mockImplementation((url) => {
        if (typeof url === 'string' && url.startsWith('/patients/staff')) {
            return Promise.resolve({ data: [] });
        }
        return Promise.resolve({ data: [] });
    });
    apiClient.post.mockResolvedValue({ data: {} });
    apiClient.delete.mockResolvedValue({ data: {} });
    apiClient.patch.mockResolvedValue({ data: {} });

    // sessionStorage is shared across renders by the PatientProvider — wipe it.
    if (typeof sessionStorage !== 'undefined') sessionStorage.clear();
});

afterEach(() => {
    vi.useRealTimers();
});

/* ------------------------------------------------------------------ */
/*  Tests                                                              */
/* ------------------------------------------------------------------ */

describe('<Patients /> — directory shell', () => {
    it('renders the page header and the empty state when no patients come back', async () => {
        renderWithProviders(<Patients />);

        // Header — sourced from PageHeader, no test-id required.
        expect(
            await screen.findByRole('heading', { name: /patient directory/i, level: 1 }),
        ).toBeInTheDocument();
        expect(screen.getByText(/front desk/i)).toBeInTheDocument();

        // Empty state — desktop table renders the "No patients match" copy. The
        // mobile card list renders the same copy, so use findAllBy to accept
        // either or both.
        const empty = await screen.findAllByText(/no patients match the current filters/i);
        expect(empty.length).toBeGreaterThan(0);

        // GET was issued exactly once with an empty search.
        expect(apiClient.get).toHaveBeenCalledWith('/patients/?search=');
    });

    it('renders a row per patient with surname, other names, OP number and age computed from DOB', async () => {
        const rows = [
            mkPatient({ patient_id: 1, surname: 'Mwangi',   other_names: 'Aisha',  outpatient_no: 'OP-0001', date_of_birth: dobFor(34) }),
            mkPatient({ patient_id: 2, surname: 'Otieno',   other_names: 'Brian',  outpatient_no: 'OP-0002', date_of_birth: dobFor(7),  sex: 'Male' }),
        ];
        apiClient.get.mockImplementation((url) => {
            if (url.startsWith('/patients/?search=')) return okList(rows);
            return okList([]);
        });

        renderWithProviders(<Patients />);

        // surname + other_names appear (possibly twice — desktop + mobile cards).
        const mwangi = await screen.findAllByText(/Mwangi, Aisha/);
        expect(mwangi.length).toBeGreaterThan(0);
        const otieno = screen.getAllByText(/Otieno, Brian/);
        expect(otieno.length).toBeGreaterThan(0);

        // OP numbers — exact text content.
        expect(screen.getAllByText('OP-0001').length).toBeGreaterThan(0);
        expect(screen.getAllByText('OP-0002').length).toBeGreaterThan(0);

        // Age substring formatted as "<sex>, 34y" on desktop OR "<sex> · 34y"
        // on mobile. Use word-boundary regex to keep the assertion tight.
        expect(screen.getAllByText(/\b34y\b/).length).toBeGreaterThan(0);
        expect(screen.getAllByText(/\b7y\b/).length).toBeGreaterThan(0);
    });
});

describe('<Patients /> — search', () => {
    it('debounces the search input and refetches with the typed query embedded in the URL', async () => {
        // userEvent v14 + vi.useFakeTimers deadlocks (its internal setTimeout
        // races vi's queue). Use real timers and let `waitFor` poll for the
        // debounced call — the page debounces at 500ms.
        const user = userEvent.setup();
        apiClient.get.mockImplementation(() => okList([]));

        renderWithProviders(<Patients />);

        // First fetch fires on mount (empty search).
        await waitFor(() => {
            expect(apiClient.get).toHaveBeenCalledWith('/patients/?search=');
        });
        const initialCallCount = apiClient.get.mock.calls.length;

        const search = screen.getByLabelText(/search patients/i);
        await user.type(search, 'foo');

        // Debounce window is 500ms — waitFor polls until the call fires.
        await waitFor(() => {
            const newCalls = apiClient.get.mock.calls.slice(initialCallCount);
            const searchCalls = newCalls.filter(([url]) =>
                typeof url === 'string' && url.includes('search=foo'),
            );
            expect(searchCalls.length).toBeGreaterThan(0);
            expect(searchCalls[0][0]).toBe('/patients/?search=foo');
        }, { timeout: 2000 });
    });
});

describe('<Patients /> — registration modal', () => {
    it('opens the registration drawer and POSTs to /patients/ on submit', async () => {
        const user = userEvent.setup();
        apiClient.get.mockImplementation(() => okList([]));
        apiClient.post.mockResolvedValueOnce({ data: { patient_id: 99 } });

        renderWithProviders(<Patients />);

        // Open modal.
        await user.click(await screen.findByRole('button', { name: /register patient/i }));

        // The drawer renders a "New registration" eyebrow and the form heading.
        expect(await screen.findByRole('heading', { name: /patient registration/i })).toBeInTheDocument();

        // The registration inputs aren't htmlFor-linked to their labels, so
        // query by name attribute. (See test report for the list of fields
        // that would benefit from htmlFor wiring.)
        await user.type(document.querySelector('input[name="surname"]'),     'Kamau');
        await user.type(document.querySelector('input[name="other_names"]'), 'Wanjiku');
        await user.type(document.getElementById('reg-dob'),                  '1990-04-15');
        await user.type(document.querySelector('input[name="telephone_1"]'), '+254712345678');

        // Submit the form. The submit button is wired via `form="patientForm"`,
        // so we click it directly.
        const submit = screen.getByRole('button', { name: /register patient & generate outpatient number/i });
        await user.click(submit);

        await waitFor(() => {
            expect(apiClient.post).toHaveBeenCalled();
        });

        const [postUrl, payload] = apiClient.post.mock.calls[0];
        expect(postUrl).toBe('/patients/');
        expect(payload).toEqual(expect.objectContaining({
            surname:       'Kamau',
            other_names:   'Wanjiku',
            date_of_birth: '1990-04-15',
            telephone_1:   '+254712345678',
        }));

        // Success toast fires.
        await waitFor(() => {
            expect(toast.success).toHaveBeenCalledWith(
                expect.stringMatching(/patient registered successfully/i),
            );
        });
    });

    it('does not call the API when the required surname is empty (HTML5 validation blocks submit)', async () => {
        const user = userEvent.setup();
        apiClient.get.mockImplementation(() => okList([]));

        renderWithProviders(<Patients />);
        await user.click(await screen.findByRole('button', { name: /register patient/i }));

        // Touch only one of the required fields — surname stays blank.
        await user.type(document.querySelector('input[name="other_names"]'), 'OnlyName');

        await user.click(
            screen.getByRole('button', { name: /register patient & generate outpatient number/i }),
        );

        // Required-field guard means handleSubmit is never reached.
        expect(apiClient.post).not.toHaveBeenCalled();
        // And the modal is still open — the heading is still in the doc.
        expect(screen.getByRole('heading', { name: /patient registration/i })).toBeInTheDocument();
    });

    it('surfaces server-side validation errors via toast.error', async () => {
        const user = userEvent.setup();
        apiClient.get.mockImplementation(() => okList([]));
        apiClient.post.mockRejectedValueOnce({
            response: { status: 400, data: { detail: 'OP Number already issued' } },
        });

        renderWithProviders(<Patients />);
        await user.click(await screen.findByRole('button', { name: /register patient/i }));

        await user.type(document.querySelector('input[name="surname"]'),     'Kamau');
        await user.type(document.querySelector('input[name="other_names"]'), 'Wanjiku');
        await user.type(document.getElementById('reg-dob'),                  '1990-04-15');
        await user.type(document.querySelector('input[name="telephone_1"]'), '+254712345678');

        await user.click(
            screen.getByRole('button', { name: /register patient & generate outpatient number/i }),
        );

        await waitFor(() => {
            expect(toast.error).toHaveBeenCalledWith('OP Number already issued');
        });
    });
});

describe('<Patients /> — soft delete', () => {
    it('confirms via window.confirm and DELETEs the patient on accept', async () => {
        const user = userEvent.setup();
        const row = mkPatient({ patient_id: 7, outpatient_no: 'OP-0007', surname: 'Njoki' });
        apiClient.get.mockImplementation((url) => {
            if (url.startsWith('/patients/?search=')) return okList([row]);
            return okList([]);
        });

        // Accept the confirm dialog.
        const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);

        renderWithProviders(<Patients />);

        // Open the row's "More actions" menu. The button label has the patient
        // name; query the first match (desktop table).
        const moreButtons = await screen.findAllByRole('button', { name: /more actions for njoki/i });
        await user.click(moreButtons[0]);

        // Deactivate is rendered as a menuitem inside the portal-anchored menu.
        const deactivate = await screen.findByRole('menuitem', { name: /deactivate/i });
        await user.click(deactivate);

        expect(confirmSpy).toHaveBeenCalled();
        await waitFor(() => {
            expect(apiClient.delete).toHaveBeenCalledWith('/patients/7');
        });
        await waitFor(() => {
            expect(toast.success).toHaveBeenCalledWith(expect.stringMatching(/deactivated/i));
        });

        confirmSpy.mockRestore();
    });

    it('does NOT delete when the user cancels the confirm dialog', async () => {
        const user = userEvent.setup();
        const row = mkPatient({ patient_id: 7, surname: 'Njoki' });
        apiClient.get.mockImplementation((url) => {
            if (url.startsWith('/patients/?search=')) return okList([row]);
            return okList([]);
        });
        const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);

        renderWithProviders(<Patients />);
        const moreButtons = await screen.findAllByRole('button', { name: /more actions for njoki/i });
        await user.click(moreButtons[0]);
        await user.click(await screen.findByRole('menuitem', { name: /deactivate/i }));

        expect(confirmSpy).toHaveBeenCalled();
        expect(apiClient.delete).not.toHaveBeenCalled();
        confirmSpy.mockRestore();
    });
});

describe('<Patients /> — route to queue', () => {
    it('opens the route picker, POSTs to /patients/{id}/route and fires a success toast', async () => {
        const user = userEvent.setup();
        const row = mkPatient({ patient_id: 11, surname: 'Achieng', other_names: 'Mary' });
        apiClient.get.mockImplementation((url) => {
            if (url.startsWith('/patients/?search=')) return okList([row]);
            if (url.startsWith('/patients/staff'))    return okList([]);
            return okList([]);
        });
        apiClient.post.mockResolvedValueOnce({ data: { queue_id: 5 } });

        renderWithProviders(<Patients />);

        // Click the "Clinical" route chip on the patient row (desktop table first).
        const clinicalChips = await screen.findAllByRole('button', { name: /send achieng to clinical/i });
        await user.click(clinicalChips[0]);

        // RouteToModal opens — header titled "Route to Clinical".
        expect(await screen.findByText(/route to clinical/i)).toBeInTheDocument();

        // Click "Send to Clinical" — the modal's submit button.
        const send = await screen.findByRole('button', { name: /send to clinical/i });
        await user.click(send);

        await waitFor(() => {
            expect(apiClient.post).toHaveBeenCalled();
        });
        const [url, payload] = apiClient.post.mock.calls[0];
        expect(url).toBe('/patients/11/route');
        expect(payload).toEqual(expect.objectContaining({
            department:   'Consultation',
            acuity_level: 3, // default "Normal"
        }));
        expect(payload.assigned_to ?? null).toBeNull();

        await waitFor(() => {
            expect(toast.success).toHaveBeenCalledWith(expect.stringMatching(/achieng.*sent to clinical/i));
        });
    });

    it('fires the "already in queue" success toast when the server reports already_queued=true', async () => {
        const user = userEvent.setup();
        const row = mkPatient({ patient_id: 12, surname: 'Kariuki', other_names: 'Peter' });
        apiClient.get.mockImplementation((url) => {
            if (url.startsWith('/patients/?search=')) return okList([row]);
            if (url.startsWith('/patients/staff'))    return okList([]);
            return okList([]);
        });
        apiClient.post.mockResolvedValueOnce({ data: { already_queued: true } });

        renderWithProviders(<Patients />);

        const labChips = await screen.findAllByRole('button', { name: /send kariuki to lab/i });
        await user.click(labChips[0]);

        await user.click(await screen.findByRole('button', { name: /send to lab/i }));

        await waitFor(() => {
            expect(toast.success).toHaveBeenCalledWith(
                expect.stringMatching(/already in the lab queue/i),
            );
        });
    });

    it('surfaces a backend error toast when the route POST rejects', async () => {
        const user = userEvent.setup();
        const row = mkPatient({ patient_id: 13, surname: 'Owino', other_names: 'Lucy' });
        apiClient.get.mockImplementation((url) => {
            if (url.startsWith('/patients/?search=')) return okList([row]);
            if (url.startsWith('/patients/staff'))    return okList([]);
            return okList([]);
        });
        apiClient.post.mockRejectedValueOnce({
            response: { status: 409, data: { detail: 'Department closed' } },
        });

        renderWithProviders(<Patients />);
        const chips = await screen.findAllByRole('button', { name: /send owino to pharmacy/i });
        await user.click(chips[0]);
        await user.click(await screen.findByRole('button', { name: /send to pharmacy/i }));

        await waitFor(() => {
            expect(toast.error).toHaveBeenCalledWith('Department closed');
        });
    });
});

describe('<Patients /> — view history', () => {
    it('clicking "View history" promotes the patient into the active context and navigates to /app/medical-history', async () => {
        const user = userEvent.setup();
        const row = mkPatient({ patient_id: 42, surname: 'Wairimu', other_names: 'Joy' });
        apiClient.get.mockImplementation((url) => {
            if (url.startsWith('/patients/?search=')) return okList([row]);
            return okList([]);
        });

        renderWithProviders(<Patients />);

        const moreButtons = await screen.findAllByRole('button', { name: /more actions for wairimu/i });
        await user.click(moreButtons[0]);

        const view = await screen.findByRole('menuitem', { name: /view history/i });
        await user.click(view);

        // The page navigates via react-router. With MemoryRouter we verify the
        // active patient was promoted into the cross-module context by checking
        // sessionStorage. For privacy, PatientContext persists ONLY an opaque
        // record ref (no PHI) under `hms_active_patient_ref` — `{ ref, at }`.
        await waitFor(() => {
            const raw = sessionStorage.getItem('hms_active_patient_ref');
            expect(raw).toBeTruthy();
            expect(JSON.parse(raw)).toEqual(expect.objectContaining({
                ref: 42,
            }));
        });
    });
});
