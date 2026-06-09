import React, { useState, useEffect, useMemo, useRef, useLayoutEffect } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { apiClient, isTenantRedirect } from '../api/client';
import toast from 'react-hot-toast';
import {
    Search, UserPlus, X, Activity, Clock, ShieldCheck, Users,
    MapPin, Phone, Briefcase, HeartPulse,
    MoreVertical, Stethoscope, TestTube, UserMinus,
    Pill, Bed, CreditCard, Printer, Download, Trash, Eye, Edit,
    AlertTriangle, Droplet, Send, Image, ChevronDown, Save,
} from 'lucide-react';
import { printPatientCard } from '../utils/printTemplates';
import PageHeader from '../components/PageHeader';
import { useActivePatient } from '../context/PatientContext';

/* ────────────────────────────────────────────────────────────────────────── */
/*  Routing destinations.                                                     */
/*                                                                            */
/*  Backend canonical names (mirror app/routes/patients.py _canonical_        */
/*  department). The friendly `label` is what the user sees; `department` is  */
/*  what we POST. Order drives the inline chip row on each patient.           */
/* ────────────────────────────────────────────────────────────────────────── */
// Each routing target carries the canonical department name, the role
// whose members should appear in the "Who?" picker, and a flag telling the
// modal whether picking a specific staff member is required, optional, or
// not applicable. Billing → cashier role; Wards/Pharmacy/Lab/Radiology
// → their respective clinical role; Clinical → Doctor.
const ROUTE_TARGETS = [
    { department: 'Triage',       label: 'Triage',    icon: HeartPulse,  role: 'Nurse',           assignment: 'optional', accent: 'bg-teal-50 text-teal-700 hover:bg-teal-100 border-teal-200' },
    { department: 'Consultation', label: 'Clinical',  icon: Stethoscope, role: 'Doctor',          assignment: 'optional', accent: 'bg-blue-50 text-blue-700 hover:bg-blue-100 border-blue-200' },
    { department: 'Laboratory',   label: 'Lab',       icon: TestTube,    role: 'Lab Technician',  assignment: 'optional', accent: 'bg-purple-50 text-purple-700 hover:bg-purple-100 border-purple-200' },
    { department: 'Radiology',    label: 'Radiology', icon: Image,       role: 'Radiologist',     assignment: 'optional', accent: 'bg-indigo-50 text-indigo-700 hover:bg-indigo-100 border-indigo-200' },
    { department: 'Pharmacy',     label: 'Pharmacy',  icon: Pill,        role: 'Pharmacist',      assignment: 'optional', accent: 'bg-accent-50 text-accent-700 hover:bg-accent-100 border-accent-200' },
    { department: 'Billing',      label: 'Billing',   icon: CreditCard,  role: 'Receptionist',    assignment: 'optional', accent: 'bg-amber-50 text-amber-700 hover:bg-amber-100 border-amber-200' },
    { department: 'Wards',        label: 'Wards',     icon: Bed,         role: 'Nurse',           assignment: 'optional', accent: 'bg-rose-50 text-rose-700 hover:bg-rose-100 border-rose-200' },
];

const initialsOf = (patient) => {
    const s = (patient?.surname || '?').trim()[0] || '?';
    const o = (patient?.other_names || '').trim()[0] || '';
    return (s + o).toUpperCase();
};

const ageFrom = (dob) => {
    if (!dob) return null;
    const birth = new Date(dob);
    if (isNaN(birth)) return null;
    const now = new Date();
    let age = now.getFullYear() - birth.getFullYear();
    const m = now.getMonth() - birth.getMonth();
    if (m < 0 || (m === 0 && now.getDate() < birth.getDate())) age -= 1;
    return age;
};

// Coerce a stored DOB into the strict YYYY-MM-DD that <input type="date">
// requires. Backend serializes a DATE column as "YYYY-MM-DD", but legacy /
// imported rows can arrive as a full ISO timestamp ("1990-05-15T00:00:00"),
// which the date input silently rejects and renders blank — and a blank value
// then gets force-sent on save and 422s the PUT. Slicing to the first 10 chars
// normalizes both shapes; anything unparseable becomes '' (left for the user).
const toDateInputValue = (dob) => {
    if (!dob) return '';
    const s = String(dob).slice(0, 10);
    return /^\d{4}-\d{2}-\d{2}$/.test(s) ? s : '';
};

// FastAPI returns 422 validation errors as an array of {loc, msg} objects, not
// a string — rendering that array straight into a toast shows "[object Object]".
// Flatten it into a readable, field-prefixed sentence.
const apiErrorMessage = (err, fallback = 'Something went wrong') => {
    const detail = err?.response?.data?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
        return detail
            .map((d) => {
                const field = Array.isArray(d.loc) ? d.loc[d.loc.length - 1] : null;
                return field ? `${field}: ${d.msg}` : d.msg;
            })
            .filter(Boolean)
            .join('; ') || fallback;
    }
    return fallback;
};

const isToday = (iso) => {
    if (!iso) return false;
    const d = new Date(iso);
    const now = new Date();
    return d.getFullYear() === now.getFullYear()
        && d.getMonth() === now.getMonth()
        && d.getDate() === now.getDate();
};

const formatRelative = (iso) => {
    if (!iso) return '—';
    const then = new Date(iso).getTime();
    const diff = Date.now() - then;
    const m = Math.floor(diff / 60000);
    if (m < 1) return 'just now';
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    const d = Math.floor(h / 24);
    if (d < 7) return `${d}d ago`;
    return new Date(iso).toLocaleDateString();
};

// Deterministic colour from the patient's name so the avatar stays stable
// across renders and pages. Cyan/teal/emerald palette feels clinical.
const AVATAR_PALETTE = [
    'bg-brand-100 text-brand-700',
    'bg-teal-100  text-teal-700',
    'bg-accent-100 text-accent-700',
    'bg-amber-100 text-amber-700',
    'bg-rose-100  text-rose-700',
    'bg-indigo-100 text-indigo-700',
    'bg-purple-100 text-purple-700',
];
const avatarColor = (key) => {
    if (!key) return AVATAR_PALETTE[0];
    let h = 0;
    for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
    return AVATAR_PALETTE[h % AVATAR_PALETTE.length];
};

// Registration form defaults — module scope so they're a stable reference, not
// rebuilt every render. Read-only (form edits create new objects via setState;
// reset re-applies these), so a shared reference is safe.
const DEFAULT_FORM_STATE = {
    surname: '', other_names: '', sex: 'Male', date_of_birth: '',
    marital_status: 'Single', religion: '', primary_language: '',
    blood_group: 'Unknown', allergies: '', chronic_conditions: '',
    id_type: 'National ID', id_number: '', nationality: 'Kenyan',
    telephone_1: '', telephone_2: '', email: '',
    postal_address: '', postal_code: '', residence: '', town: '',
    occupation: '', employer_name: '', reference_number: '',
    nok_name: '', nok_relationship: '', nok_contact: '', notes: ''
};
// KDPA Section 30 — treatment consent captured inline at registration.
// Default given + Verbal (how walk-ins work); clinician can adjust.
const DEFAULT_CONSENT_STATE = { given: true, method: 'Verbal' };

export default function Patients() {
    const [patients, setPatients] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [searchQuery, setSearchQuery] = useState('');
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [isSubmitting, setIsSubmitting] = useState(false);

    // Interactive States
    // Active dropdown carries both the patient id (to drive which row's
    // trigger highlights) AND the trigger DOM node, which the portal-based
    // RowMenu uses to anchor itself in the viewport. Storing the DOM node
    // in state is intentional: refs can't be enumerated across many rows,
    // but capturing event.currentTarget on click works for every row with
    // zero ref bookkeeping.
    const [activeDropdown, setActiveDropdown] = useState(null);  // null | { patientId, anchorEl }
    const [sexFilter, setSexFilter] = useState('');
    const [routingId, setRoutingId] = useState(null);
    const navigate = useNavigate();
    const { setActivePatient } = useActivePatient();

    const closeDropdown = () => setActiveDropdown(null);
    const toggleDropdown = (patientId, e) => {
        // Capture the DOM node NOW. React 18 zeroes out `e.currentTarget`
        // after the handler returns, and our updater fn runs during the
        // next render — by then `e.currentTarget` would be null, the menu
        // would anchor at viewport (0,0), and the doc-level click-outside
        // listener would see the trigger as "not inside the anchor" and
        // close the menu the moment it opened.
        const anchorEl = e.currentTarget;
        // Stop the synthetic click from bubbling to the doc-level
        // mousedown/click listener the menu installs — the same physical
        // click would otherwise be treated as "outside" the menu.
        e.stopPropagation();
        setActiveDropdown(prev =>
            prev?.patientId === patientId ? null : { patientId, anchorEl }
        );
    };

    // Form State (defaults at module scope — see DEFAULT_FORM_STATE)
    const [formData, setFormData] = useState(DEFAULT_FORM_STATE);
    // Many patients (esp. older walk-ins) have no email. Default to "no email"
    // and only reveal the field when the receptionist marks one as available,
    // so a blank email is an explicit choice rather than a skipped field.
    const [regHasEmail, setRegHasEmail] = useState(false);

    // KDPA Section 30 — Treatment consent must exist before any clinical
    // write. We capture it inline at registration so the patient is
    // consent-active by the time anyone tries to record vitals / notes /
    // prescriptions. Persisted separately from the patient row via a
    // follow-up POST to /medical-history/consent — the Patient schema
    // doesn't carry these fields. Default checked + Verbal because that's
    // how walk-in registrations work in practice; the clinician can
    // uncheck and capture written consent later if the patient hasn't
    // agreed yet.
    const [consentForm, setConsentForm] = useState(DEFAULT_CONSENT_STATE);

    useEffect(() => {
        const delayDebounce = setTimeout(() => fetchPatients(), 500);
        return () => clearTimeout(delayDebounce);
    }, [searchQuery]);

    const fetchPatients = async () => {
        setIsLoading(true);
        try {
            const response = await apiClient.get(`/patients/?search=${encodeURIComponent(searchQuery)}`);
            setPatients(response.data);
        } catch (error) {
            // Suppress the toast when the client is in the middle of
            // redirecting to /portal (tenant guard) — the page is about
            // to unmount anyway and a flashing toast looks like a bug.
            if (isTenantRedirect(error)) return;

            const status = error.response?.status;
            const serverDetail = error.response?.data?.detail;
            let msg;
            if (!status) {
                msg = 'Cannot reach the server. Retrying shortly…';
            } else if (status === 401) {
                msg = 'Your session has expired — sign in again.';
            } else if (status === 403) {
                msg = `Access denied: ${serverDetail || 'you do not have the patients:read permission.'}`;
            } else if (status === 402) {
                msg = serverDetail || 'Patient Registry is not in your package — contact MediFleet support.';
            } else {
                msg = serverDetail || `Failed to load patients (HTTP ${status}).`;
            }
            toast.error(msg);
        } finally {
            setIsLoading(false);
        }
    };

    const handleInputChange = (e) => {
        setFormData({ ...formData, [e.target.name]: e.target.value });
    };

    // ── Bidirectional age ↔ DOB sync ─────────────────────────────────────
    // Doctors / receptionists often only know the approximate age (common
    // when a Kenyan ID has been lost or the patient is a child). Typing an
    // age sets DOB to "today minus N years" so the rest of the form can
    // proceed; a tooltip on the field reminds the operator to confirm the
    // exact date with the patient when known.
    const computeDobFromAge = (age) => {
        const n = parseInt(age, 10);
        if (Number.isNaN(n) || n < 0 || n > 130) return '';
        const d = new Date();
        d.setFullYear(d.getFullYear() - n);
        const pad = (v) => String(v).padStart(2, '0');
        return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    };

    const ageFromDobStr = (dob) => {
        if (!dob) return '';
        const birth = new Date(dob);
        if (Number.isNaN(birth.getTime())) return '';
        const now = new Date();
        let age = now.getFullYear() - birth.getFullYear();
        const m = now.getMonth() - birth.getMonth();
        if (m < 0 || (m === 0 && now.getDate() < birth.getDate())) age -= 1;
        return age >= 0 ? String(age) : '';
    };

    // The form holds DOB as the source of truth. `ageDisplay` is a derived
    // string that lives next to it; editing either updates the other.
    const [ageDisplay, setAgeDisplay] = useState('');

    // Whenever DOB changes from outside the age field (e.g. opening for a
    // new registration), re-derive the age so the two stay coherent.
    useEffect(() => {
        setAgeDisplay(ageFromDobStr(formData.date_of_birth));
    }, [formData.date_of_birth]);

    // Minors usually have no National ID — a Birth Certificate is the right
    // document. When the patient resolves to under 18 and the operator hasn't
    // already chosen a specific ID type, nudge the default to Birth
    // Certificate. We only switch *away* from the untouched default, so every
    // other ID type (Passport, Alien ID, …) stays selectable and a manual
    // pick is never overridden.
    useEffect(() => {
        const age = parseInt(ageFromDobStr(formData.date_of_birth), 10);
        if (!Number.isNaN(age) && age < 18 && formData.id_type === 'National ID') {
            setFormData(f => ({ ...f, id_type: 'Birth Certificate' }));
        }
    }, [formData.date_of_birth]); // eslint-disable-line react-hooks/exhaustive-deps

    const handleAgeChange = (e) => {
        const raw = e.target.value;
        setAgeDisplay(raw);
        const dob = computeDobFromAge(raw);
        // Only push back into DOB if we got a sensible number; otherwise
        // leave the existing DOB untouched so the operator doesn't lose
        // a previously-picked date by accidentally typing a letter.
        if (raw === '' || dob) {
            setFormData(f => ({ ...f, date_of_birth: dob || f.date_of_birth }));
        }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();

        // ID number is optional (efficiency for the Kenyan market — minors and
        // no-ID walk-ins are common). We never block on a missing ID; the
        // operator gets an inline hint while filling the form and a warning
        // toast on success so it isn't silently forgotten.
        const hasIdNumber = !!formData.id_number?.trim();
        const noIdWarning = !hasIdNumber && formData.id_type !== 'None';

        // When ID Type is "None", never carry a stale typed number through.
        const payload = formData.id_type === 'None'
            ? { ...formData, id_number: '' }
            : formData;

        setIsSubmitting(true);
        try {
            const created = await apiClient.post('/patients/', payload);
            const newPatientId = created?.data?.patient_id ?? created?.data?.id;
            toast.success("Patient registered successfully & OP Number generated.");
            if (noIdWarning) {
                toast('Registered without an ID number — add it later when available.', { icon: '⚠️' });
            }

            // KDPA Section 30 follow-up: if the receptionist captured a
            // Treatment consent on the form, record it now so the next
            // clinical write doesn't 403. Failure here is non-fatal —
            // the patient row already exists; clinicians can record
            // consent later via the Medical History page.
            if (newPatientId && consentForm.given) {
                try {
                    await apiClient.post('/medical-history/consent', {
                        patient_id: newPatientId,
                        consent_type: 'Treatment',
                        consent_given: true,
                        consent_method: consentForm.method || 'Verbal',
                        notes: 'Captured at patient registration.',
                    });
                } catch (consentErr) {
                    toast.error(
                        'Patient saved, but treatment consent failed to record. '
                        + 'Record it from Medical History before adding clinical notes.'
                    );
                }
            }

            setIsModalOpen(false);
            setFormData(DEFAULT_FORM_STATE);
            setRegHasEmail(false);
            setConsentForm(DEFAULT_CONSENT_STATE);
            fetchPatients();
        } catch (error) {
            toast.error(error.response?.data?.detail || "Registration failed");
        } finally {
            setIsSubmitting(false);
        }
    };

    // --- Action: Route Patient ---
    // Two-step flow: click a route chip → open the picker modal so the
    // receptionist can pick *which* staff member to assign the patient to.
    // The actual POST happens from inside the modal once the picker
    // confirms (or skips, in which case the row lands in the unassigned
    // pool so any qualified clinician can claim it).
    const [routeRequest, setRouteRequest] = useState(null); // { patient, target } | null
    // Edit modal state. Holds the patient object being edited — null means
    // closed. The modal owns its own form state so the parent doesn't have
    // to track every keystroke, and a successful PUT triggers fetchPatients().
    const [editingPatient, setEditingPatient] = useState(null);
    const openEditModal = (patient) => {
        closeDropdown();
        setEditingPatient(patient);
    };
    const closeEditModal = () => setEditingPatient(null);
    const handlePatientUpdated = async () => {
        await fetchPatients();
        closeEditModal();
    };

    const openRoutePicker = (patient, target) => {
        setRouteRequest({ patient, target });
    };

    const submitRoute = async ({ patient, target, assigned_to, acuity = 3 }) => {
        const { department, label } = target;
        setRoutingId(`${patient.patient_id}:${department}`);
        try {
            const res = await apiClient.post(`/patients/${patient.patient_id}/route`, {
                department,
                acuity_level: acuity,
                assigned_to: assigned_to ?? null,
            });
            const alreadyQueued = res.data?.already_queued;
            const name = `${patient.surname}, ${patient.other_names}`;
            toast.success(
                alreadyQueued
                    ? `${name} is already in the ${label} queue.`
                    : `${name} sent to ${label}${assigned_to ? '' : ' (unassigned)'}.`,
            );
            setRouteRequest(null);
        } catch (error) {
            toast.error(error.response?.data?.detail || `Failed to route to ${label}.`);
        } finally {
            setRoutingId(null);
        }
    };

    // --- Action: View History ---
    // Opening a chart promotes the patient into the cross-module active
    // context so the bar persists as the user navigates around the system,
    // and the KDPA S.26 access log captures every module visit.
    const viewHistory = (patientId) => {
        setActiveDropdown(null);
        const patient = patients.find(p => p.patient_id === patientId);
        if (patient) setActivePatient(patient);
        navigate(`/app/medical-history?patient_id=${patientId}`);
    };

    // --- Action: Deactivate Patient ---
    const deactivatePatient = async (patientId) => {
        if (!window.confirm("Are you sure you want to deactivate this patient record?")) return;

        try {
            await apiClient.delete(`/patients/${patientId}`);
            toast.success("Patient record deactivated.");
            setActiveDropdown(null);
            fetchPatients();
        } catch (error) {
            toast.error("Failed to deactivate patient.");
        }
    };

    // --- Action: Export Patient Data (KDPA S.26 Subject Access Request) ---
    const exportPatientData = async (patient) => {
        setActiveDropdown(null);
        try {
            const res = await apiClient.get(`/privacy/patients/${patient.patient_id}/export`);
            const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `patient_${patient.outpatient_no}_export.json`;
            a.click();
            URL.revokeObjectURL(url);
            toast.success('Patient data export ready.');
        } catch (error) {
            toast.error(error.response?.data?.detail || 'Export failed.');
        }
    };

    // --- Action: Right to Erasure (KDPA S.40 Anonymization) ---
    const erasePatient = async (patient) => {
        setActiveDropdown(null);
        const confirmation = window.prompt(
            `KDPA Right to Erasure — this will anonymize "${patient.surname}, ${patient.other_names}". `
            + `Clinical records remain (Health Act 2017 retention). To confirm, retype the OP number: ${patient.outpatient_no}`
        );
        if (!confirmation) return;
        const reason = window.prompt('Reason for erasure (auditable):', 'Subject request');
        if (!reason) return;

        try {
            await apiClient.post(`/privacy/patients/${patient.patient_id}/erase`, {
                reason,
                confirm_outpatient_no: confirmation,
            });
            toast.success('Patient anonymized per KDPA S.40.');
            fetchPatients();
        } catch (error) {
            toast.error(error.response?.data?.detail || 'Erasure failed.');
        }
    };

    // Client-side filter applied on top of the server's search results.
    const visiblePatients = useMemo(() => (
        sexFilter ? patients.filter(p => p.sex === sexFilter) : patients
    ), [patients, sexFilter]);

    // Aggregate stats for the strip at the top of the directory.
    const stats = useMemo(() => {
        const today = patients.filter(p => isToday(p.registered_on)).length;
        const female = patients.filter(p => p.sex === 'Female').length;
        const male = patients.filter(p => p.sex === 'Male').length;
        const withAllergies = patients.filter(p => p.allergies && p.allergies.trim()).length;
        return { total: patients.length, today, female, male, withAllergies };
    }, [patients]);

    return (
        <div className="space-y-6">
            <PageHeader
                eyebrow="Front desk"
                icon={Users}
                title="Patient Directory"
                subtitle="Register, search, and route patients across departmental queues."
                tone="brand"
                actions={
                    <button
                        data-tour="register-patient"
                        type="button"
                        onClick={() => setIsModalOpen(true)}
                        className="btn-primary cursor-pointer"
                    >
                        <UserPlus size={16} aria-hidden="true" /> Register patient
                    </button>
                }
            />

            {/* ── Stat strip ──────────────────────────────────────────────── */}
            <div data-tour="patients-stats" className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
                <DirectoryStat label="Active patients"      value={stats.total}          icon={Users}        accent="brand" />
                <DirectoryStat label="Registered today"     value={stats.today}          icon={UserPlus}     accent="accent" />
                <DirectoryStat label="Female"               value={stats.female}         icon={Users}        accent="rose" />
                <DirectoryStat label="Male"                 value={stats.male}           icon={Users}        accent="teal" />
                <DirectoryStat label="Allergy flagged"      value={stats.withAllergies}  icon={AlertTriangle} accent="amber" />
            </div>

            {/* ── Toolbar: search + filter ───────────────────────────────── */}
            <div data-tour="patient-search" className="card p-3 sm:p-4 flex flex-col sm:flex-row sm:items-center gap-3">
                <div className="relative flex-1 min-w-0">
                    <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" aria-hidden="true" />
                    <label htmlFor="patient-search" className="sr-only">Search patients</label>
                    <input
                        id="patient-search"
                        type="search"
                        placeholder="Search by OP Number, name, ID, or phone…"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        className="input pl-10"
                    />
                </div>
                <div data-tour="patients-filter-chips" className="flex items-center gap-2" role="tablist" aria-label="Filter by sex">
                    {['', 'Male', 'Female'].map(s => (
                        <button
                            key={s || 'all'}
                            type="button"
                            onClick={() => setSexFilter(s)}
                            role="tab"
                            aria-selected={sexFilter === s}
                            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors cursor-pointer ${
                                sexFilter === s
                                    ? 'bg-brand-50 text-brand-700 ring-1 ring-brand-200'
                                    : 'text-ink-700 dark:text-ink-300 hover:bg-ink-50 dark:hover:bg-ink-800/50'
                            }`}
                        >
                            {s || 'All'}
                        </button>
                    ))}
                </div>
                <div className="text-xs text-ink-500 sm:ml-2 shrink-0">
                    {visiblePatients.length} of {patients.length} record{patients.length === 1 ? '' : 's'}
                </div>
            </div>

            {/* ── Desktop table (md+) ─────────────────────────────────────── */}
            <div className="hidden md:block card overflow-visible">
                <div className="overflow-x-auto overflow-y-visible">
                    <table className="w-full text-left text-sm">
                        <thead className="bg-ink-50 dark:bg-ink-900/40 text-ink-600 dark:text-ink-400 text-2xs uppercase font-semibold tracking-[0.14em]">
                            <tr>
                                <th className="px-5 py-3">Patient</th>
                                <th className="px-5 py-3">Contact</th>
                                <th className="px-5 py-3">Vitals</th>
                                <th className="px-5 py-3">Route to queue</th>
                                <th className="px-5 py-3 text-right">Manage</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-ink-100 dark:divide-ink-800 text-ink-700 dark:text-ink-300">
                            {isLoading ? (
                                <tr>
                                    <td colSpan="5" className="px-6 py-12 text-center text-ink-500">
                                        <Activity className="animate-spin inline mr-2 text-brand-600" size={20} aria-hidden="true" />
                                        Loading patient records…
                                    </td>
                                </tr>
                            ) : visiblePatients.length === 0 ? (
                                <tr>
                                    <td colSpan="5" className="px-6 py-16 text-center text-ink-500">
                                        <Users size={36} className="mx-auto mb-2 text-ink-300" aria-hidden="true" />
                                        <p className="text-sm font-medium text-ink-700 dark:text-ink-300">No patients match the current filters.</p>
                                        <p className="text-xs mt-1">Try clearing the search or registering a new patient.</p>
                                    </td>
                                </tr>
                            ) : (
                                visiblePatients.map(patient => {
                                    const age = ageFrom(patient.date_of_birth);
                                    const hasAllergies = patient.allergies && patient.allergies.trim();
                                    return (
                                        <tr key={patient.patient_id} className="hover:bg-ink-50/60 transition-colors">
                                            {/* Patient */}
                                            <td className="px-5 py-3 align-top">
                                                <div className="flex items-start gap-3">
                                                    <div className={`shrink-0 size-10 rounded-full flex items-center justify-center text-sm font-semibold ${avatarColor(patient.outpatient_no)}`} aria-hidden="true">
                                                        {initialsOf(patient)}
                                                    </div>
                                                    <div className="min-w-0">
                                                        <div className="font-semibold text-ink-900 dark:text-ink-100 truncate">{patient.surname}, {patient.other_names}</div>
                                                        <div className="flex items-center gap-2 text-xs text-ink-500 mt-0.5">
                                                            <span className="font-mono text-brand-700">{patient.outpatient_no}</span>
                                                            <span aria-hidden="true">·</span>
                                                            <span>{patient.sex}{age !== null ? `, ${age}y` : ''}</span>
                                                        </div>
                                                    </div>
                                                </div>
                                            </td>

                                            {/* Contact */}
                                            <td className="px-5 py-3 align-top text-xs">
                                                <div className="flex items-center gap-1.5 text-ink-700 dark:text-ink-300">
                                                    <Phone size={12} className="text-ink-400 shrink-0" aria-hidden="true" />
                                                    <span className="truncate">{patient.telephone_1 || '—'}</span>
                                                </div>
                                                <div className="flex items-center gap-1.5 text-ink-500 mt-1">
                                                    <MapPin size={12} className="text-ink-400 shrink-0" aria-hidden="true" />
                                                    <span className="truncate">{patient.residence || patient.town || 'Unspecified'}</span>
                                                </div>
                                                <div className="text-2xs text-ink-400 mt-1" title={patient.registered_on ? new Date(patient.registered_on).toLocaleString() : ''}>
                                                    Registered {formatRelative(patient.registered_on)}
                                                </div>
                                            </td>

                                            {/* Vitals */}
                                            <td className="px-5 py-3 align-top text-xs">
                                                <div className="flex items-center gap-1.5 text-ink-700 dark:text-ink-300">
                                                    <Droplet size={12} className="text-rose-500 shrink-0" aria-hidden="true" />
                                                    <span>{patient.blood_group && patient.blood_group !== 'Unknown' ? patient.blood_group : 'Unknown'}</span>
                                                </div>
                                                <div className="mt-1 min-h-[1rem]">
                                                    {hasAllergies ? (
                                                        <span className="badge-warn inline-flex items-center gap-1" title={patient.allergies}>
                                                            <AlertTriangle size={10} aria-hidden="true" /> Allergies
                                                        </span>
                                                    ) : (
                                                        <span className="text-ink-400 text-2xs">No allergies</span>
                                                    )}
                                                </div>
                                            </td>

                                            {/* Route to queue */}
                                            <td className="px-5 py-3 align-top">
                                                <div data-tour="patient-row-route-chips" className="flex flex-wrap gap-1">
                                                    {ROUTE_TARGETS.map(t => {
                                                        const Icon = t.icon;
                                                        const busy = routingId === `${patient.patient_id}:${t.department}`;
                                                        return (
                                                            <button
                                                                key={t.department}
                                                                type="button"
                                                                onClick={() => openRoutePicker(patient, t)}
                                                                disabled={busy}
                                                                aria-label={`Send ${patient.surname} to ${t.label}`}
                                                                title={`Send to ${t.label}`}
                                                                className={`inline-flex items-center gap-1 px-2 py-1 rounded-md text-2xs font-semibold border transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ${t.accent}`}
                                                            >
                                                                {busy
                                                                    ? <Activity size={11} className="animate-spin" aria-hidden="true" />
                                                                    : <Icon size={11} aria-hidden="true" />}
                                                                <span>{t.label}</span>
                                                            </button>
                                                        );
                                                    })}
                                                </div>
                                            </td>

                                            {/* Manage dropdown */}
                                            <td className="px-5 py-3 text-right align-top">
                                                <button
                                                    type="button"
                                                    data-tour="patient-row-more"
                                                    onClick={(e) => toggleDropdown(patient.patient_id, e)}
                                                    aria-label={`More actions for ${patient.surname}, ${patient.other_names}`}
                                                    aria-haspopup="menu"
                                                    aria-expanded={activeDropdown?.patientId === patient.patient_id}
                                                    className="p-2 text-ink-500 hover:text-brand-600 hover:bg-brand-50 rounded-lg transition-colors cursor-pointer"
                                                >
                                                    <MoreVertical size={16} aria-hidden="true" />
                                                </button>
                                            </td>
                                        </tr>
                                    );
                                })
                            )}
                        </tbody>
                    </table>
                </div>
            </div>

            {/* ── Mobile cards ─────────────────────────────────────────────── */}
            <div className="md:hidden space-y-3">
                {isLoading ? (
                    <div className="card p-8 text-center text-ink-500">
                        <Activity className="animate-spin inline mr-2 text-brand-600" size={20} aria-hidden="true" /> Loading…
                    </div>
                ) : visiblePatients.length === 0 ? (
                    <div className="card p-8 text-center text-ink-500">
                        <Users size={32} className="mx-auto mb-2 text-ink-300" aria-hidden="true" />
                        <p className="text-sm font-medium text-ink-700 dark:text-ink-300">No patients match the current filters.</p>
                    </div>
                ) : (
                    visiblePatients.map(patient => {
                        const age = ageFrom(patient.date_of_birth);
                        const hasAllergies = patient.allergies && patient.allergies.trim();
                        return (
                            <article key={patient.patient_id} className="card p-4">
                                <header className="flex items-start gap-3">
                                    <div className={`shrink-0 size-11 rounded-full flex items-center justify-center text-sm font-semibold ${avatarColor(patient.outpatient_no)}`} aria-hidden="true">
                                        {initialsOf(patient)}
                                    </div>
                                    <div className="min-w-0 flex-1">
                                        <h3 className="font-semibold text-ink-900 dark:text-ink-100 truncate">{patient.surname}, {patient.other_names}</h3>
                                        <div className="text-xs text-ink-500 mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5">
                                            <span className="font-mono text-brand-700">{patient.outpatient_no}</span>
                                            <span>{patient.sex}{age !== null ? ` · ${age}y` : ''}</span>
                                            {hasAllergies && (
                                                <span className="badge-warn inline-flex items-center gap-1">
                                                    <AlertTriangle size={10} aria-hidden="true" /> Allergies
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                    <button
                                        type="button"
                                        onClick={(e) => toggleDropdown(patient.patient_id, e)}
                                        aria-label={`More actions for ${patient.surname}`}
                                        aria-haspopup="menu"
                                        aria-expanded={activeDropdown?.patientId === patient.patient_id}
                                        className="shrink-0 size-11 inline-flex items-center justify-center text-ink-500 hover:text-brand-600 hover:bg-brand-50 rounded-lg cursor-pointer"
                                    >
                                        <MoreVertical size={18} aria-hidden="true" />
                                    </button>
                                </header>

                                <dl className="mt-3 grid grid-cols-2 gap-2 text-xs">
                                    <div>
                                        <dt className="text-ink-500">Phone</dt>
                                        <dd className="text-ink-900 dark:text-ink-100 flex items-center gap-1 mt-0.5">
                                            <Phone size={11} className="text-ink-400" aria-hidden="true" />
                                            <span className="truncate">{patient.telephone_1 || '—'}</span>
                                        </dd>
                                    </div>
                                    <div>
                                        <dt className="text-ink-500">Residence</dt>
                                        <dd className="text-ink-900 dark:text-ink-100 flex items-center gap-1 mt-0.5">
                                            <MapPin size={11} className="text-ink-400" aria-hidden="true" />
                                            <span className="truncate">{patient.residence || patient.town || '—'}</span>
                                        </dd>
                                    </div>
                                    <div>
                                        <dt className="text-ink-500">Blood</dt>
                                        <dd className="text-ink-900 dark:text-ink-100 flex items-center gap-1 mt-0.5">
                                            <Droplet size={11} className="text-rose-500" aria-hidden="true" />
                                            {patient.blood_group && patient.blood_group !== 'Unknown' ? patient.blood_group : 'Unknown'}
                                        </dd>
                                    </div>
                                    <div>
                                        <dt className="text-ink-500">Registered</dt>
                                        <dd className="text-ink-900 dark:text-ink-100 mt-0.5" title={patient.registered_on ? new Date(patient.registered_on).toLocaleString() : ''}>
                                            {formatRelative(patient.registered_on)}
                                        </dd>
                                    </div>
                                </dl>

                                <div className="mt-3">
                                    <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-500 mb-1.5">Route to queue</p>
                                    <div className="flex flex-wrap gap-1.5">
                                        {ROUTE_TARGETS.map(t => {
                                            const Icon = t.icon;
                                            const busy = routingId === `${patient.patient_id}:${t.department}`;
                                            return (
                                                <button
                                                    key={t.department}
                                                    type="button"
                                                    onClick={() => openRoutePicker(patient, t)}
                                                    disabled={busy}
                                                    aria-label={`Send ${patient.surname} to ${t.label}`}
                                                    className={`inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md text-2xs font-semibold border transition-colors cursor-pointer disabled:opacity-50 ${t.accent}`}
                                                >
                                                    {busy
                                                        ? <Activity size={11} className="animate-spin" aria-hidden="true" />
                                                        : <Icon size={11} aria-hidden="true" />}
                                                    <span>{t.label}</span>
                                                </button>
                                            );
                                        })}
                                    </div>
                                </div>
                            </article>
                        );
                    })
                )}
            </div>

            {/* --- History Drawer removed in favor of full Medical History module --- */}

            {/* Slide-over Modal for Registration */}
            {isModalOpen && (
                <div className="fixed inset-0 z-50 overflow-hidden flex justify-end">
                    <div className="fixed inset-0 bg-ink-900/60 backdrop-blur-sm" onClick={() => setIsModalOpen(false)}></div>

                    <div className="relative w-full max-w-4xl bg-white dark:bg-ink-900 h-full shadow-elevated flex flex-col animate-slide-in-right">
                        <div className="flex items-center justify-between p-6 border-b border-ink-100 dark:border-ink-800 bg-white dark:bg-ink-900 shrink-0">
                            <div>
                                <span className="section-eyebrow">New registration</span>
                                <h2 className="text-xl font-semibold text-ink-900 dark:text-ink-100 tracking-tight mt-1 flex items-center gap-2">
                                    <UserPlus className="text-brand-600" size={20} />
                                    Patient registration
                                </h2>
                                <p className="text-sm text-ink-500 mt-1">Complete the form to generate an Outpatient Number.</p>
                            </div>
                            <button onClick={() => setIsModalOpen(false)} aria-label="Close" className="text-ink-400 hover:text-ink-700 p-2 hover:bg-ink-100 dark:hover:bg-ink-800 rounded-full transition-colors">
                                <X size={20} />
                            </button>
                        </div>

                        <div className="flex-1 overflow-y-auto p-6 bg-ink-50/60 custom-scrollbar">
                            <form id="patientForm" onSubmit={handleSubmit} className="space-y-6">
                                
                                {/* SECTION 1: Identity */}
                                <div className="card p-5 sm:p-6">
                                    <h3 className="section-eyebrow text-brand-700 mb-4 border-b border-ink-100 dark:border-ink-800 pb-3 flex items-center gap-2">
                                        <ShieldCheck size={16} /> Identity & Demographics
                                    </h3>
                                    <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                                        <div className="md:col-span-2">
                                            <label htmlFor="reg-surname" className="label">Surname <span className="text-red-500">*</span></label>
                                            <input required id="reg-surname" type="text" name="surname" value={formData.surname} onChange={handleInputChange} className="input" />
                                        </div>
                                        <div className="md:col-span-2">
                                            <label htmlFor="reg-other-names" className="label">Other Names <span className="text-red-500">*</span></label>
                                            <input required id="reg-other-names" type="text" name="other_names" value={formData.other_names} onChange={handleInputChange} className="input" />
                                        </div>
                                        <div>
                                            <label htmlFor="reg-sex" className="label">Sex <span className="text-red-500">*</span></label>
                                            <select id="reg-sex" name="sex" value={formData.sex} onChange={handleInputChange} className="input">
                                                <option>Male</option>
                                                <option>Female</option>
                                            </select>
                                        </div>
                                        <div>
                                            <label className="label" htmlFor="reg-dob">Date of Birth <span className="text-red-500">*</span></label>
                                            <input
                                                id="reg-dob"
                                                required
                                                type="date"
                                                name="date_of_birth"
                                                value={formData.date_of_birth}
                                                onChange={handleInputChange}
                                                max={new Date().toISOString().slice(0, 10)}
                                                className="input"
                                            />
                                        </div>
                                        <div>
                                            <label className="label flex items-center gap-1" htmlFor="reg-age">
                                                Age
                                                <span className="text-2xs font-normal text-ink-400 normal-case tracking-normal">(years)</span>
                                            </label>
                                            <input
                                                id="reg-age"
                                                type="number"
                                                min="0"
                                                max="130"
                                                step="1"
                                                inputMode="numeric"
                                                value={ageDisplay}
                                                onChange={handleAgeChange}
                                                placeholder="e.g. 34"
                                                className="input"
                                                title="Type the age if exact DOB is unknown — DOB auto-fills to today minus N years. Confirm with patient."
                                            />
                                            {ageDisplay && !formData.date_of_birth && (
                                                <p className="helper text-amber-700">Approximated DOB — confirm with patient when possible.</p>
                                            )}
                                        </div>
                                        <div>
                                            <label htmlFor="reg-id-type" className="label">ID Type</label>
                                            <select id="reg-id-type" name="id_type" value={formData.id_type} onChange={handleInputChange} className="input">
                                                <option>National ID</option>
                                                <option>Passport</option>
                                                <option>Birth Certificate</option>
                                                <option>Alien ID</option>
                                                <option>None</option>
                                            </select>
                                        </div>
                                        <div>
                                            <label htmlFor="reg-id-number" className="label">ID Number</label>
                                            <input
                                                id="reg-id-number"
                                                type="text"
                                                name="id_number"
                                                value={formData.id_number}
                                                onChange={handleInputChange}
                                                className="input"
                                                disabled={formData.id_type === 'None'}
                                                placeholder={formData.id_type === 'None' ? 'No ID on file' : ''}
                                            />
                                            {/* Kenya: many walk-in patients (minors, no-ID adults) have no
                                                document. Don't block — just nudge, so it isn't forgotten. */}
                                            {formData.id_type !== 'None' && !formData.id_number.trim() && (
                                                <p className="helper text-amber-700">
                                                    No ID number — you can still register; add it later, or set ID Type to “None”.
                                                </p>
                                            )}
                                        </div>
                                        <div>
                                            <label htmlFor="reg-nationality" className="label">Nationality</label>
                                            <input id="reg-nationality" type="text" name="nationality" value={formData.nationality} onChange={handleInputChange} className="input" />
                                        </div>
                                        <div>
                                            <label htmlFor="reg-marital" className="label">Marital Status</label>
                                            <select id="reg-marital" name="marital_status" value={formData.marital_status} onChange={handleInputChange} className="input">
                                                <option>Single</option>
                                                <option>Married</option>
                                                <option>Divorced</option>
                                                <option>Widowed</option>
                                            </select>
                                        </div>
                                        <div>
                                            <label htmlFor="reg-religion" className="label">Religion</label>
                                            <input id="reg-religion" type="text" name="religion" value={formData.religion} onChange={handleInputChange} className="input" />
                                        </div>
                                        <div>
                                            <label htmlFor="reg-language" className="label">Primary Language</label>
                                            <input id="reg-language" type="text" name="primary_language" value={formData.primary_language} onChange={handleInputChange} className="input" />
                                        </div>
                                    </div>
                                </div>

                                {/* SECTION 2: Contact & Location */}
                                <div className="card p-5 sm:p-6">
                                    <h3 className="section-eyebrow text-brand-700 mb-4 border-b border-ink-100 dark:border-ink-800 pb-3 flex items-center gap-2">
                                        <MapPin size={16} /> Contact & Location
                                    </h3>
                                    <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                                        <div>
                                            <label htmlFor="reg-tel-1" className="label">Primary Phone <span className="text-red-500">*</span></label>
                                            <input required id="reg-tel-1" type="text" name="telephone_1" value={formData.telephone_1} onChange={handleInputChange} className="input" />
                                        </div>
                                        <div>
                                            <label htmlFor="reg-tel-2" className="label">Alternative Phone</label>
                                            <input id="reg-tel-2" type="text" name="telephone_2" value={formData.telephone_2} onChange={handleInputChange} className="input" />
                                        </div>
                                        <div className="md:col-span-2">
                                            <label htmlFor="reg-email-avail" className="label">Email Address</label>
                                            <select
                                                id="reg-email-avail"
                                                value={regHasEmail ? 'available' : 'none'}
                                                onChange={(e) => {
                                                    const has = e.target.value === 'available';
                                                    setRegHasEmail(has);
                                                    if (!has) setFormData(f => ({ ...f, email: '' }));
                                                }}
                                                className="input"
                                            >
                                                <option value="none">No email address</option>
                                                <option value="available">Has an email address</option>
                                            </select>
                                            {regHasEmail && (
                                                <input id="reg-email" type="email" name="email" value={formData.email} onChange={handleInputChange} placeholder="patient@example.com" className="input mt-2" />
                                            )}
                                        </div>
                                        <div className="md:col-span-2">
                                            <label htmlFor="reg-residence" className="label">Residence (Estate/Area)</label>
                                            <input id="reg-residence" type="text" name="residence" value={formData.residence} onChange={handleInputChange} className="input" />
                                        </div>
                                        <div>
                                            <label htmlFor="reg-town" className="label">Town</label>
                                            <input id="reg-town" type="text" name="town" value={formData.town} onChange={handleInputChange} className="input" />
                                        </div>
                                        <div>
                                            <label htmlFor="reg-postal" className="label">Postal Address</label>
                                            <input id="reg-postal" type="text" name="postal_address" value={formData.postal_address} onChange={handleInputChange} className="input" placeholder="P.O Box - Code" />
                                        </div>
                                    </div>
                                </div>

                                {/* SECTION 3: Employment & Next of Kin */}
                                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                                    <div className="card p-5 sm:p-6">
                                        <h3 className="section-eyebrow text-brand-700 mb-4 border-b border-ink-100 dark:border-ink-800 pb-3 flex items-center gap-2">
                                            <Briefcase size={16} /> Employment
                                        </h3>
                                        <div className="space-y-4">
                                            <div>
                                                <label htmlFor="reg-occupation" className="label">Occupation</label>
                                                <input id="reg-occupation" type="text" name="occupation" value={formData.occupation} onChange={handleInputChange} className="input" />
                                            </div>
                                            <div>
                                                <label htmlFor="reg-employer" className="label">Employer Name</label>
                                                <input id="reg-employer" type="text" name="employer_name" value={formData.employer_name} onChange={handleInputChange} className="input" />
                                            </div>
                                            <div>
                                                <label htmlFor="reg-ref-no" className="label">Reference/Staff Number</label>
                                                <input id="reg-ref-no" type="text" name="reference_number" value={formData.reference_number} onChange={handleInputChange} className="input" />
                                            </div>
                                        </div>
                                    </div>
                                    <div className="card p-5 sm:p-6">
                                        <h3 className="section-eyebrow text-brand-700 mb-4 border-b border-ink-100 dark:border-ink-800 pb-3 flex items-center gap-2">
                                            <Phone size={16} /> Next of Kin
                                        </h3>
                                        <div className="space-y-4">
                                            <div>
                                                <label htmlFor="reg-nok-name" className="label">NOK Name</label>
                                                <input id="reg-nok-name" type="text" name="nok_name" value={formData.nok_name} onChange={handleInputChange} className="input" />
                                            </div>
                                            <div>
                                                <label htmlFor="reg-nok-rel" className="label">Relationship</label>
                                                <input id="reg-nok-rel" type="text" name="nok_relationship" value={formData.nok_relationship} onChange={handleInputChange} className="input" />
                                            </div>
                                            <div>
                                                <label htmlFor="reg-nok-contact" className="label">NOK Contact Number</label>
                                                <input id="reg-nok-contact" type="text" name="nok_contact" value={formData.nok_contact} onChange={handleInputChange} className="input" />
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                {/* SECTION 4: Clinical Baselines & Notes */}
                                <div className="card p-5 sm:p-6">
                                    <h3 className="section-eyebrow text-brand-700 mb-4 border-b border-ink-100 dark:border-ink-800 pb-3 flex items-center gap-2">
                                        <HeartPulse size={16} /> Clinical Baselines & Notes
                                    </h3>
                                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                        <div>
                                            <label htmlFor="reg-blood-group" className="label">Blood Group</label>
                                            <select id="reg-blood-group" name="blood_group" value={formData.blood_group} onChange={handleInputChange} className="input">
                                                <option>Unknown</option><option>A+</option><option>A-</option>
                                                <option>B+</option><option>B-</option><option>O+</option>
                                                <option>O-</option><option>AB+</option><option>AB-</option>
                                            </select>
                                        </div>
                                        <div className="md:col-span-2">
                                            <label htmlFor="reg-allergies" className="label">Known Allergies</label>
                                            <input id="reg-allergies" type="text" name="allergies" value={formData.allergies} onChange={handleInputChange} className="input" placeholder="e.g., Penicillin, Peanuts" />
                                        </div>
                                        <div className="md:col-span-3">
                                            <label htmlFor="reg-chronic" className="label">Chronic Conditions</label>
                                            <input id="reg-chronic" type="text" name="chronic_conditions" value={formData.chronic_conditions} onChange={handleInputChange} className="input" placeholder="e.g., Hypertension, Type 2 Diabetes" />
                                        </div>
                                        <div className="md:col-span-3">
                                            <label htmlFor="reg-notes" className="label">Front Desk Notes</label>
                                            <textarea id="reg-notes" name="notes" value={formData.notes} onChange={handleInputChange} rows="2" className="input" placeholder="Any additional registration remarks..." />
                                        </div>
                                    </div>
                                </div>

                                {/* SECTION 4: KDPA Section 30 — Treatment consent */}
                                <div className="p-5 rounded-xl border border-amber-200 bg-amber-50/40">
                                    <div className="flex items-start gap-3">
                                        <input
                                            id="reg-consent"
                                            type="checkbox"
                                            checked={consentForm.given}
                                            onChange={(e) => setConsentForm(c => ({ ...c, given: e.target.checked }))}
                                            className="mt-1"
                                        />
                                        <div className="flex-1">
                                            <label htmlFor="reg-consent" className="font-medium text-ink-900 dark:text-ink-100 cursor-pointer">
                                                Patient has consented to treatment (KDPA Section 30)
                                            </label>
                                            <p className="text-xs text-ink-600 dark:text-ink-400 mt-1">
                                                Required before clinicians can record any clinical entry. Uncheck only if the patient hasn't agreed yet — you can capture written consent later from the Medical History page.
                                            </p>
                                            <div className="mt-3 flex items-center gap-2">
                                                <label htmlFor="reg-consent-method" className="text-xs text-ink-600 dark:text-ink-400">Method:</label>
                                                <select
                                                    id="reg-consent-method"
                                                    value={consentForm.method}
                                                    onChange={(e) => setConsentForm(c => ({ ...c, method: e.target.value }))}
                                                    disabled={!consentForm.given}
                                                    className="input py-1.5 text-xs max-w-[10rem]"
                                                >
                                                    <option value="Verbal">Verbal</option>
                                                    <option value="Written">Written</option>
                                                    <option value="Electronic">Electronic</option>
                                                </select>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                            </form>
                        </div>

                        <div className="p-5 border-t border-ink-100 dark:border-ink-800 bg-white dark:bg-ink-900 flex gap-3 shrink-0">
                            <button type="button" onClick={() => setIsModalOpen(false)} className="btn-secondary">
                                Cancel
                            </button>
                            <button type="submit" form="patientForm" disabled={isSubmitting} className="btn-primary flex-1 py-3">
                                {isSubmitting ? (
                                    <><Activity className="animate-spin" size={16} /> Processing&hellip;</>
                                ) : (
                                    'Register patient & generate Outpatient Number'
                                )}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Route-to picker modal — opens when the front desk clicks
                any route chip. Lets them pick a specific staff member to
                assign the patient to within that module. */}
            {routeRequest && (
                <RouteToModal
                    patient={routeRequest.patient}
                    target={routeRequest.target}
                    busy={routingId === `${routeRequest.patient.patient_id}:${routeRequest.target.department}`}
                    onSubmit={(payload) => submitRoute({
                        patient: routeRequest.patient,
                        target: routeRequest.target,
                        ...payload,
                    })}
                    onClose={() => setRouteRequest(null)}
                />
            )}

            {/* Singleton portal-anchored row menu — exactly one instance
                rendered when *some* row's More button is active. Portaled
                to <body> so no ancestor's overflow can clip it. */}
            {activeDropdown && (() => {
                const open = patients.find(p => p.patient_id === activeDropdown.patientId);
                if (!open) return null;
                return (
                    <RowMenu
                        patient={open}
                        anchorEl={activeDropdown.anchorEl}
                        onClose={closeDropdown}
                        onView={viewHistory}
                        onEdit={openEditModal}
                        onPrint={(p) => { printPatientCard(p); closeDropdown(); }}
                        onExport={exportPatientData}
                        onDeactivate={deactivatePatient}
                        onErase={erasePatient}
                    />
                );
            })()}

            {editingPatient && (
                <EditPatientModal
                    patient={editingPatient}
                    onClose={closeEditModal}
                    onSaved={handlePatientUpdated}
                />
            )}
        </div>
    );
}

const STAT_ACCENTS = {
    brand:  'bg-brand-50  text-brand-700  ring-brand-100',
    teal:   'bg-teal-50   text-teal-700   ring-teal-100',
    accent: 'bg-accent-50 text-accent-700 ring-accent-100',
    amber:  'bg-amber-50  text-amber-700  ring-amber-100',
    rose:   'bg-rose-50   text-rose-700   ring-rose-100',
};

function DirectoryStat({ label, value, icon: Icon, accent = 'brand' }) {
    return (
        <div className="stat-tile">
            <div className={`stat-icon ${STAT_ACCENTS[accent] || STAT_ACCENTS.brand}`} aria-hidden="true">
                <Icon size={18} />
            </div>
            <div className="min-w-0">
                <p className="stat-label truncate">{label}</p>
                <p className="stat-value tabular-nums">{value}</p>
            </div>
        </div>
    );
}

/**
 * RouteToModal — "Who should this patient see?" picker.
 *
 * Fetches active staff for the destination's role via /api/patients/staff,
 * lets the receptionist either pick a specific person or send unassigned
 * (any qualified clinician can claim the row). Triage acuity is exposed so
 * the front desk can mark genuine emergencies — the clinical queue is
 * ordered by acuity ascending before joined_at, so a "Critical" patient
 * jumps the queue.
 */
const ACUITY_PRESETS = [
    { value: 1, label: 'Critical',  hint: 'Resuscitate now',     className: 'bg-rose-50 text-rose-800 border-rose-200' },
    { value: 2, label: 'High',      hint: 'See within 10 min',   className: 'bg-amber-50 text-amber-800 border-amber-200' },
    { value: 3, label: 'Normal',    hint: 'Routine triage',      className: 'bg-brand-50 text-brand-800 border-brand-200' },
    { value: 4, label: 'Low',       hint: 'Can wait',            className: 'bg-ink-50 dark:bg-ink-900/40 text-ink-700 dark:text-ink-300 border-ink-200 dark:border-ink-800' },
    { value: 5, label: 'Non-urgent', hint: 'Walk-in',            className: 'bg-ink-50 dark:bg-ink-900/40 text-ink-700 dark:text-ink-300 border-ink-200 dark:border-ink-800' },
];

function RouteToModal({ patient, target, busy, onSubmit, onClose }) {
    const [staff, setStaff] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [selectedId, setSelectedId] = useState('');
    const [acuity, setAcuity] = useState(3);
    const [search, setSearch] = useState('');

    useEffect(() => {
        let cancelled = false;
        setIsLoading(true);
        apiClient.get('/patients/staff', { params: target.role ? { role: target.role } : {} })
            .then(res => { if (!cancelled) setStaff(res.data || []); })
            .catch(() => { if (!cancelled) setStaff([]); })
            .finally(() => { if (!cancelled) setIsLoading(false); });
        return () => { cancelled = true; };
    }, [target.role]);

    const filtered = useMemo(() => {
        const needle = search.trim().toLowerCase();
        if (!needle) return staff;
        return staff.filter(s =>
            s.full_name?.toLowerCase().includes(needle)
            || (s.specialization || '').toLowerCase().includes(needle)
        );
    }, [staff, search]);

    const Icon = target.icon;

    const send = () => {
        onSubmit({
            assigned_to: selectedId ? parseInt(selectedId, 10) : null,
            acuity,
        });
    };

    const fullName = `${patient.surname}, ${patient.other_names}`;
    const noRoleMatch = !isLoading && staff.length === 0;

    return (
        <div
            className="fixed inset-0 z-[55] flex items-center justify-center p-3 sm:p-4 bg-ink-950/60 backdrop-blur-sm animate-fade-in"
            role="dialog"
            aria-modal="true"
            aria-labelledby="route-modal-title"
        >
            <div className="bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-800 rounded-2xl shadow-elevated w-full max-w-lg max-h-[calc(100vh-1.5rem)] flex flex-col overflow-hidden animate-slide-up">
                {/* Header */}
                <div className="px-4 sm:px-6 py-4 border-b border-ink-200 dark:border-ink-800 bg-ink-50 dark:bg-ink-900/40 flex justify-between items-start gap-3 shrink-0">
                    <div className="min-w-0 flex items-start gap-3">
                        <div className={`shrink-0 size-10 rounded-xl border flex items-center justify-center ${target.accent}`} aria-hidden="true">
                            <Icon size={18} />
                        </div>
                        <div className="min-w-0">
                            <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-brand-700">Route to {target.label}</p>
                            <h2 id="route-modal-title" className="text-base font-semibold text-ink-900 dark:text-ink-100 tracking-tight truncate">{fullName}</h2>
                            <p className="text-xs text-ink-500 mt-0.5 font-mono">{patient.outpatient_no}</p>
                        </div>
                    </div>
                    <button
                        type="button"
                        onClick={onClose}
                        aria-label="Close"
                        className="p-2 rounded-lg text-ink-500 hover:text-ink-900 hover:bg-ink-100 dark:hover:bg-ink-800 cursor-pointer shrink-0"
                    >
                        <X size={18} aria-hidden="true" />
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto custom-scrollbar p-4 sm:p-6 space-y-4">
                    {/* Acuity */}
                    <div>
                        <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-700 dark:text-ink-300 mb-1.5">Triage acuity</p>
                        <div className="grid grid-cols-2 sm:grid-cols-5 gap-1.5" role="radiogroup" aria-label="Triage acuity">
                            {ACUITY_PRESETS.map(p => {
                                const active = acuity === p.value;
                                return (
                                    <button
                                        key={p.value}
                                        type="button"
                                        role="radio"
                                        aria-checked={active}
                                        onClick={() => setAcuity(p.value)}
                                        title={p.hint}
                                        className={`rounded-md border px-2 py-1.5 text-left transition-colors cursor-pointer ${
                                            active ? `${p.className} ring-2 ring-offset-1 ring-brand-500/20 font-semibold` : 'bg-white dark:bg-ink-900 border-ink-200 dark:border-ink-800 hover:bg-ink-50 dark:hover:bg-ink-800/50 text-ink-700 dark:text-ink-300'
                                        }`}
                                    >
                                        <p className="text-2xs font-semibold uppercase tracking-wider">{p.label}</p>
                                        <p className="text-[10px] text-ink-500 truncate">{p.hint}</p>
                                    </button>
                                );
                            })}
                        </div>
                    </div>

                    {/* Staff picker */}
                    <div>
                        <div className="flex items-center justify-between mb-1.5">
                            <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-700 dark:text-ink-300">
                                Assign to {target.role ? <span className="text-ink-500 normal-case tracking-normal">({target.role})</span> : ''}
                            </p>
                            <span className="text-2xs text-ink-500">{isLoading ? 'Loading…' : `${filtered.length} available`}</span>
                        </div>

                        {/* Search — only show when more than a handful of staff */}
                        {staff.length > 5 && (
                            <div className="relative mb-2">
                                <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-400" aria-hidden="true" />
                                <label htmlFor="route-staff-search" className="sr-only">Search staff</label>
                                <input
                                    id="route-staff-search"
                                    type="search"
                                    value={search}
                                    onChange={(e) => setSearch(e.target.value)}
                                    placeholder="Search by name or specialization…"
                                    className="w-full bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-800 rounded-lg pl-8 pr-3 py-1.5 text-xs text-ink-900 dark:text-ink-100 placeholder-ink-400 focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
                                />
                            </div>
                        )}

                        {/* Unassigned option — first row, always visible */}
                        <label
                            htmlFor="staff-none"
                            className={`flex items-center justify-between gap-2 rounded-lg border px-3 py-2 cursor-pointer transition-colors ${
                                selectedId === ''
                                    ? 'bg-brand-50/60 border-brand-200'
                                    : 'bg-white dark:bg-ink-900 border-ink-200 dark:border-ink-800 hover:bg-ink-50 dark:hover:bg-ink-800/50'
                            }`}
                        >
                            <span className="flex items-center gap-2 min-w-0">
                                <input
                                    id="staff-none"
                                    type="radio"
                                    name="route-staff"
                                    value=""
                                    checked={selectedId === ''}
                                    onChange={() => setSelectedId('')}
                                    className="accent-brand-600"
                                />
                                <span className="text-sm font-medium text-ink-900 dark:text-ink-100">Send unassigned</span>
                            </span>
                            <span className="text-2xs text-ink-500">Anyone on the {target.label} queue can claim</span>
                        </label>

                        {/* Staff list */}
                        <div className="mt-1.5 max-h-64 overflow-y-auto custom-scrollbar rounded-lg border border-ink-200 dark:border-ink-800 divide-y divide-ink-100 dark:divide-ink-800">
                            {isLoading ? (
                                <div className="p-6 text-center text-ink-500 text-sm">
                                    <Activity className="animate-spin inline mr-2 text-brand-600" size={16} aria-hidden="true" /> Loading staff…
                                </div>
                            ) : noRoleMatch ? (
                                <p className="p-4 text-center text-xs text-ink-500">
                                    No active {target.role}s configured. The patient will land unassigned —
                                    any qualified clinician can pick them up from the {target.label} queue.
                                </p>
                            ) : filtered.length === 0 ? (
                                <p className="p-4 text-center text-xs text-ink-500">No staff match "{search}".</p>
                            ) : filtered.map(s => {
                                const isPicked = selectedId === String(s.user_id);
                                return (
                                    <label
                                        key={s.user_id}
                                        htmlFor={`staff-${s.user_id}`}
                                        className={`flex items-center justify-between gap-2 px-3 py-2 cursor-pointer transition-colors ${
                                            isPicked ? 'bg-brand-50/60' : 'hover:bg-ink-50 dark:hover:bg-ink-800/50'
                                        }`}
                                    >
                                        <span className="flex items-center gap-2 min-w-0">
                                            <input
                                                id={`staff-${s.user_id}`}
                                                type="radio"
                                                name="route-staff"
                                                value={String(s.user_id)}
                                                checked={isPicked}
                                                onChange={() => setSelectedId(String(s.user_id))}
                                                className="accent-brand-600"
                                            />
                                            <span className="min-w-0">
                                                <span className="block text-sm font-medium text-ink-900 dark:text-ink-100 truncate">{s.full_name}</span>
                                                {s.specialization && (
                                                    <span className="block text-2xs text-ink-500 truncate">{s.specialization}</span>
                                                )}
                                            </span>
                                        </span>
                                        {s.role && <span className="text-2xs text-ink-500 shrink-0">{s.role}</span>}
                                    </label>
                                );
                            })}
                        </div>
                    </div>
                </div>

                {/* Footer */}
                <div className="px-4 sm:px-6 py-3 border-t border-ink-200 dark:border-ink-800 bg-ink-50 dark:bg-ink-900/40 flex flex-col-reverse sm:flex-row sm:justify-end gap-2 shrink-0">
                    <button type="button" onClick={onClose} className="btn-secondary cursor-pointer">Cancel</button>
                    <button
                        type="button"
                        onClick={send}
                        disabled={busy}
                        className="btn-primary disabled:opacity-50 cursor-pointer"
                    >
                        {busy
                            ? <><Activity size={15} className="animate-spin" aria-hidden="true" /> Routing…</>
                            : <><Send size={15} aria-hidden="true" /> Send to {target.label}</>}
                    </button>
                </div>
            </div>
        </div>
    );
}

/**
 * RowMenu — portal-rendered "Manage" dropdown.
 *
 * Why a portal: the desktop table sits inside `<div className="overflow-x-auto">`
 * because the columns can overflow on smaller windows. CSS resolves `overflow-y`
 * to `auto` whenever `overflow-x` isn't `visible`, so an absolute child gets
 * clipped vertically — that's why the old menu hid its last items. Rendering
 * into <body> with `position: fixed` sidesteps every ancestor's overflow.
 *
 * Positioning: anchor to the trigger button's bounding rect. Right-align with
 * the trigger, drop below by 6px, clamp inside the viewport, and flip above
 * the trigger if the bottom of the menu would otherwise spill off-screen.
 */
const MENU_WIDTH = 232;
const MENU_MARGIN = 8;

function RowMenu({ patient, anchorEl, onClose, onView, onEdit, onPrint, onExport, onDeactivate, onErase }) {
    const menuRef = useRef(null);
    const [pos, setPos] = useState({ top: 0, left: 0, ready: false });

    const recompute = () => {
        if (!anchorEl) return;
        const r = anchorEl.getBoundingClientRect();
        const vw = window.innerWidth;
        const vh = window.innerHeight;
        const menuH = menuRef.current?.offsetHeight || 280;

        // Right-align with the trigger, then clamp to viewport.
        let left = r.right - MENU_WIDTH;
        if (left < MENU_MARGIN) left = MENU_MARGIN;
        if (left + MENU_WIDTH + MENU_MARGIN > vw) left = vw - MENU_WIDTH - MENU_MARGIN;

        // Prefer below; flip above when the menu would spill off the bottom.
        let top = r.bottom + 6;
        if (top + menuH + MENU_MARGIN > vh) {
            const flipped = r.top - menuH - 6;
            top = flipped >= MENU_MARGIN ? flipped : Math.max(MENU_MARGIN, vh - menuH - MENU_MARGIN);
        }

        setPos({ top, left, ready: true });
    };

    useLayoutEffect(() => { recompute();   }, [anchorEl]);

    useEffect(() => {
        // Recompute on scroll (capture so we catch scrolling ancestors too)
        // and on resize so the menu doesn't drift when the user rotates a
        // tablet or resizes the window.
        const onScroll = () => recompute();
        const onResize = () => recompute();
        const onKey = (e) => { if (e.key === 'Escape') onClose(); };
        const onDocClick = (e) => {
            if (menuRef.current?.contains(e.target)) return;
            if (anchorEl?.contains?.(e.target)) return;
            onClose();
        };
        window.addEventListener('scroll', onScroll, true);
        window.addEventListener('resize', onResize);
        document.addEventListener('keydown', onKey);
        document.addEventListener('mousedown', onDocClick);
        document.addEventListener('touchstart', onDocClick);
        return () => {
            window.removeEventListener('scroll', onScroll, true);
            window.removeEventListener('resize', onResize);
            document.removeEventListener('keydown', onKey);
            document.removeEventListener('mousedown', onDocClick);
            document.removeEventListener('touchstart', onDocClick);
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [anchorEl, onClose]);

    if (typeof document === 'undefined') return null;

    return createPortal(
        <div
            ref={menuRef}
            role="menu"
            aria-label="Patient actions"
            style={{
                position: 'fixed',
                top: pos.top,
                left: pos.left,
                width: MENU_WIDTH,
                opacity: pos.ready ? 1 : 0,
            }}
            className="bg-white dark:bg-ink-900 rounded-xl shadow-elevated border border-ink-200 dark:border-ink-800 py-2 z-[60] text-left animate-fade-in"
        >
            <div className="px-3 pt-1 pb-1.5 text-2xs font-semibold text-ink-500 uppercase tracking-[0.14em]">Manage</div>
            <button type="button" role="menuitem" onClick={() => onView(patient.patient_id)} className="w-full px-3.5 py-2 text-sm text-ink-700 dark:text-ink-300 hover:bg-ink-50 dark:hover:bg-ink-800/50 flex items-center gap-2.5 cursor-pointer">
                <Eye size={15} className="text-ink-500" aria-hidden="true" /> View history
            </button>
            <button type="button" role="menuitem" onClick={() => onEdit(patient)} className="w-full px-3.5 py-2 text-sm text-ink-700 dark:text-ink-300 hover:bg-ink-50 dark:hover:bg-ink-800/50 flex items-center gap-2.5 cursor-pointer">
                <Edit size={15} className="text-ink-500" aria-hidden="true" /> Edit details
            </button>
            <button type="button" role="menuitem" onClick={() => onPrint(patient)} className="w-full px-3.5 py-2 text-sm text-ink-700 dark:text-ink-300 hover:bg-ink-50 dark:hover:bg-ink-800/50 flex items-center gap-2.5 cursor-pointer">
                <Printer size={15} className="text-ink-500" aria-hidden="true" /> Print card
            </button>
            <button type="button" role="menuitem" onClick={() => onExport(patient)} className="w-full px-3.5 py-2 text-sm text-ink-700 dark:text-ink-300 hover:bg-ink-50 dark:hover:bg-ink-800/50 flex items-center gap-2.5 cursor-pointer">
                <Download size={15} className="text-ink-500" aria-hidden="true" /> Export (KDPA S.26)
            </button>
            <div className="border-t border-ink-100 dark:border-ink-800 my-1.5" role="separator" />
            <button type="button" role="menuitem" onClick={() => onDeactivate(patient.patient_id)} className="w-full px-3.5 py-2 text-sm text-rose-600 hover:bg-rose-50 flex items-center gap-2.5 cursor-pointer">
                <UserMinus size={15} aria-hidden="true" /> Deactivate
            </button>
            <button type="button" role="menuitem" onClick={() => onErase(patient)} className="w-full px-3.5 py-2 text-sm text-rose-700 hover:bg-rose-50 flex items-center gap-2.5 font-semibold cursor-pointer">
                <Trash size={15} aria-hidden="true" /> Erase (KDPA S.40)
            </button>
        </div>,
        document.body
    );
}

/**
 * EditPatientModal — focused editor for the fields most commonly corrected
 * after registration (typos in name, missing phone, updated next-of-kin,
 * blood group / allergies / chronic conditions discovered at the first
 * encounter).
 *
 * Only fields in PatientUpdate are PUT — schema strict-mode would reject
 * unknown keys. Sensitive identifiers (id_number, dob) are intentionally
 * kept here because front-desk frequently mis-keys them at registration
 * and the audit trail captures every change anyway.
 */
function EditPatientModal({ patient, onClose, onSaved }) {
    const [form, setForm] = useState({
        surname:           patient.surname           ?? '',
        other_names:       patient.other_names       ?? '',
        sex:               patient.sex               ?? 'Male',
        date_of_birth:     toDateInputValue(patient.date_of_birth),
        marital_status:    patient.marital_status    ?? 'Single',
        blood_group:       patient.blood_group       ?? 'Unknown',
        allergies:         patient.allergies         ?? '',
        chronic_conditions: patient.chronic_conditions ?? '',
        id_type:           patient.id_type           ?? 'National ID',
        id_number:         patient.id_number         ?? '',
        nationality:       patient.nationality       ?? 'Kenyan',
        telephone_1:       patient.telephone_1       ?? '',
        telephone_2:       patient.telephone_2       ?? '',
        email:             patient.email             ?? '',
        residence:         patient.residence         ?? '',
        town:              patient.town              ?? '',
        occupation:        patient.occupation        ?? '',
        nok_name:          patient.nok_name          ?? '',
        nok_relationship:  patient.nok_relationship  ?? '',
        nok_contact:       patient.nok_contact       ?? '',
        notes:             patient.notes             ?? '',
    });
    const [isSubmitting, setIsSubmitting] = useState(false);
    // Mirror the registration UX: a patient may simply have no email. Seed the
    // toggle from the existing record so editing a patient who has one keeps it
    // visible, while a patient without one starts collapsed.
    const [editHasEmail, setEditHasEmail] = useState(Boolean(patient.email));
    const handle = (e) => {
        const { name, value } = e.target;
        setForm(f => {
            const next = { ...f, [name]: value };
            // Mirror the registration nudge: if a DOB edit resolves the patient
            // to under 18 and the ID type is still the untouched "National ID"
            // default, suggest "Birth Certificate". Only fires on an actual DOB
            // edit (never on open), only switches away from the default, and
            // leaves every other ID type a manual override.
            if (name === 'date_of_birth') {
                const age = ageFrom(value);
                if (age !== null && age < 18 && f.id_type === 'National ID') {
                    next.id_type = 'Birth Certificate';
                }
            }
            return next;
        });
    };

    const submit = async (e) => {
        e.preventDefault();
        setIsSubmitting(true);
        try {
            // Strip empty optional fields so we don't overwrite existing
            // values with "" on a save the user didn't intend to clear.
            // surname/other_names/sex stay even if blank so the backend sees the
            // intended values; date_of_birth is deliberately NOT force-kept —
            // an empty date string fails strict date validation (422), so we
            // simply omit it when blank and leave the stored DOB untouched.
            const KEEP_EMPTY = new Set(['surname', 'other_names', 'sex']);
            const payload = Object.fromEntries(
                Object.entries(form).filter(([k, v]) =>
                    KEEP_EMPTY.has(k) || (v !== '' && v !== null && v !== undefined)
                )
            );
            // If the user marked "No email address", send an explicit null so a
            // previously-stored email is actually cleared (the blank-strip above
            // would otherwise omit the field and leave the old value in place).
            if (!editHasEmail) payload.email = null;
            await apiClient.put(`/patients/${patient.patient_id}`, payload);
            toast.success('Patient updated.');
            await onSaved();
        } catch (err) {
            toast.error(apiErrorMessage(err, 'Update failed'));
        } finally {
            setIsSubmitting(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <div className="fixed inset-0 bg-ink-900/60 backdrop-blur-sm" onClick={onClose} />
            <div className="relative bg-white dark:bg-ink-900 rounded-2xl shadow-elevated w-full max-w-3xl max-h-[90vh] flex flex-col">
                <div className="flex items-center justify-between p-5 border-b border-ink-100 dark:border-ink-800 shrink-0">
                    <div>
                        <h3 className="text-lg font-semibold text-ink-900 dark:text-ink-100">Edit patient</h3>
                        <p className="text-xs text-ink-500 mt-0.5 font-mono">{patient.outpatient_no}</p>
                    </div>
                    <button onClick={onClose} aria-label="Close" className="text-ink-400 hover:text-ink-700 p-2 hover:bg-ink-100 dark:hover:bg-ink-800 rounded-full transition-colors">
                        <X size={18} />
                    </button>
                </div>

                <form id="editPatientForm" onSubmit={submit} className="p-5 space-y-5 overflow-y-auto">
                    {/* Demographics */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                        <div><label className="label">Surname</label><input name="surname" value={form.surname} onChange={handle} className="input" required /></div>
                        <div><label className="label">Other names</label><input name="other_names" value={form.other_names} onChange={handle} className="input" required /></div>
                        <div><label className="label">Sex</label>
                            <select name="sex" value={form.sex} onChange={handle} className="input">
                                <option>Male</option><option>Female</option><option>Other</option>
                            </select>
                        </div>
                        <div><label className="label">Date of birth</label><input type="date" name="date_of_birth" value={form.date_of_birth} onChange={handle} className="input" /></div>
                        <div><label className="label">Marital status</label>
                            <select name="marital_status" value={form.marital_status} onChange={handle} className="input">
                                <option>Single</option><option>Married</option><option>Divorced</option><option>Widowed</option><option>Other</option>
                            </select>
                        </div>
                        <div><label className="label">Nationality</label><input name="nationality" value={form.nationality} onChange={handle} className="input" /></div>
                    </div>

                    {/* Clinical */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                        <div>
                            <label className="label">Blood group</label>
                            <select name="blood_group" value={form.blood_group} onChange={handle} className="input">
                                {['Unknown','A+','A-','B+','B-','AB+','AB-','O+','O-'].map(g => <option key={g}>{g}</option>)}
                            </select>
                        </div>
                        <div className="md:col-span-2"><label className="label">Allergies</label><input name="allergies" value={form.allergies} onChange={handle} className="input" placeholder="e.g., Penicillin, Peanuts" /></div>
                        <div className="md:col-span-3"><label className="label">Chronic conditions</label><input name="chronic_conditions" value={form.chronic_conditions} onChange={handle} className="input" placeholder="e.g., Hypertension, Type 2 Diabetes" /></div>
                    </div>

                    {/* ID */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                        <div>
                            <label className="label">ID type</label>
                            <select name="id_type" value={form.id_type} onChange={handle} className="input">
                                <option>National ID</option><option>Passport</option><option>Alien ID</option><option>Birth Certificate</option><option>None</option><option>Other</option>
                            </select>
                        </div>
                        <div className="md:col-span-2"><label className="label">ID number</label><input name="id_number" value={form.id_number} onChange={handle} className="input" /></div>
                    </div>

                    {/* Contact */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <div><label className="label">Phone 1</label><input name="telephone_1" value={form.telephone_1} onChange={handle} className="input" /></div>
                        <div><label className="label">Phone 2</label><input name="telephone_2" value={form.telephone_2} onChange={handle} className="input" /></div>
                        <div className="md:col-span-2">
                            <label className="label">Email</label>
                            <select
                                value={editHasEmail ? 'available' : 'none'}
                                onChange={(e) => {
                                    const has = e.target.value === 'available';
                                    setEditHasEmail(has);
                                    if (!has) setForm(f => ({ ...f, email: '' }));
                                }}
                                className="input"
                            >
                                <option value="none">No email address</option>
                                <option value="available">Has an email address</option>
                            </select>
                            {editHasEmail && (
                                <input type="email" name="email" value={form.email} onChange={handle} placeholder="patient@example.com" className="input mt-2" />
                            )}
                        </div>
                        <div><label className="label">Residence</label><input name="residence" value={form.residence} onChange={handle} className="input" /></div>
                        <div><label className="label">Town</label><input name="town" value={form.town} onChange={handle} className="input" /></div>
                    </div>

                    {/* Employment & NOK */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                        <div className="md:col-span-3"><label className="label">Occupation</label><input name="occupation" value={form.occupation} onChange={handle} className="input" /></div>
                        <div><label className="label">Next of kin</label><input name="nok_name" value={form.nok_name} onChange={handle} className="input" /></div>
                        <div><label className="label">Relationship</label><input name="nok_relationship" value={form.nok_relationship} onChange={handle} className="input" /></div>
                        <div><label className="label">NoK contact</label><input name="nok_contact" value={form.nok_contact} onChange={handle} className="input" /></div>
                    </div>

                    {/* Notes */}
                    <div>
                        <label className="label">Front desk notes</label>
                        <textarea name="notes" value={form.notes} onChange={handle} rows="2" className="input" />
                    </div>
                </form>

                <div className="p-5 border-t border-ink-100 dark:border-ink-800 bg-white dark:bg-ink-900 flex gap-3 shrink-0">
                    <button type="button" onClick={onClose} className="btn-secondary">Cancel</button>
                    <button type="submit" form="editPatientForm" disabled={isSubmitting} className="btn-primary flex-1 py-3">
                        {isSubmitting ? (<><Activity className="animate-spin" size={16} /> Saving…</>) : (<><Save size={16} /> Save changes</>)}
                    </button>
                </div>
            </div>
        </div>
    );
}
