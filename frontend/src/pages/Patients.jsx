import React, { useState, useEffect, useMemo, useRef, useLayoutEffect } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { apiClient, isTenantRedirect } from '../api/client';
import toast from 'react-hot-toast';
import {
    Search, UserPlus, X, Activity, Clock, ShieldCheck, Users,
    MapPin, Phone, Briefcase, HeartPulse,
    MoreVertical, Stethoscope, TestTube, UserMinus,
    Pill, Bed, CreditCard, Printer, Download, Trash, Eye,
    AlertTriangle, Droplet, Send, Image, ChevronDown,
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
const ROUTE_TARGETS = [
    { department: 'Consultation', label: 'Clinical',  icon: Stethoscope, accent: 'bg-blue-50 text-blue-700 hover:bg-blue-100 border-blue-200' },
    { department: 'Laboratory',   label: 'Lab',       icon: TestTube,    accent: 'bg-purple-50 text-purple-700 hover:bg-purple-100 border-purple-200' },
    { department: 'Radiology',    label: 'Radiology', icon: Image,       accent: 'bg-indigo-50 text-indigo-700 hover:bg-indigo-100 border-indigo-200' },
    { department: 'Pharmacy',     label: 'Pharmacy',  icon: Pill,        accent: 'bg-accent-50 text-accent-700 hover:bg-accent-100 border-accent-200' },
    { department: 'Billing',      label: 'Billing',   icon: CreditCard,  accent: 'bg-amber-50 text-amber-700 hover:bg-amber-100 border-amber-200' },
    { department: 'Wards',        label: 'Wards',     icon: Bed,         accent: 'bg-rose-50 text-rose-700 hover:bg-rose-100 border-rose-200' },
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
        setActiveDropdown(prev =>
            prev?.patientId === patientId ? null : { patientId, anchorEl: e.currentTarget }
        );
    };

    // Form State
    const defaultFormState = {
        surname: '', other_names: '', sex: 'Male', date_of_birth: '',
        marital_status: 'Single', religion: '', primary_language: '',
        blood_group: 'Unknown', allergies: '', chronic_conditions: '',
        id_type: 'National ID', id_number: '', nationality: 'Kenyan',
        telephone_1: '', telephone_2: '', email: '',
        postal_address: '', postal_code: '', residence: '', town: '',
        occupation: '', employer_name: '', reference_number: '',
        nok_name: '', nok_relationship: '', nok_contact: '', notes: ''
    };
    const [formData, setFormData] = useState(defaultFormState);

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
        setIsSubmitting(true);
        try {
            await apiClient.post('/patients/', formData);
            toast.success("Patient registered successfully & OP Number generated.");
            setIsModalOpen(false);
            setFormData(defaultFormState);
            fetchPatients();
        } catch (error) {
            toast.error(error.response?.data?.detail || "Registration failed");
        } finally {
            setIsSubmitting(false);
        }
    };

    // --- Action: Route Patient ---
    // Sends the canonical department name (resolved server-side; the backend
    // also accepts UI synonyms but we send the canonical here so analytics +
    // queue lookups match without a round trip). On success the response
    // includes the queue_id so we could deep-link to it later — for now we
    // just surface a toast and close the menu.
    const routePatient = async (patient, target) => {
        const { department, label } = target;
        setRoutingId(`${patient.patient_id}:${department}`);
        try {
            const res = await apiClient.post(`/patients/${patient.patient_id}/route`, {
                department,
                acuity_level: 3,
            });
            const alreadyQueued = res.data?.already_queued;
            const name = `${patient.surname}, ${patient.other_names}`;
            toast[alreadyQueued ? 'success' : 'success'](
                alreadyQueued
                    ? `${name} is already in the ${label} queue.`
                    : `${name} sent to ${label}.`,
            );
            setActiveDropdown(null);
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
                        type="button"
                        onClick={() => setIsModalOpen(true)}
                        className="btn-primary cursor-pointer"
                    >
                        <UserPlus size={16} aria-hidden="true" /> Register patient
                    </button>
                }
            />

            {/* ── Stat strip ──────────────────────────────────────────────── */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
                <DirectoryStat label="Active patients"      value={stats.total}          icon={Users}        accent="brand" />
                <DirectoryStat label="Registered today"     value={stats.today}          icon={UserPlus}     accent="accent" />
                <DirectoryStat label="Female"               value={stats.female}         icon={Users}        accent="rose" />
                <DirectoryStat label="Male"                 value={stats.male}           icon={Users}        accent="teal" />
                <DirectoryStat label="Allergy flagged"      value={stats.withAllergies}  icon={AlertTriangle} accent="amber" />
            </div>

            {/* ── Toolbar: search + filter ───────────────────────────────── */}
            <div className="card p-3 sm:p-4 flex flex-col sm:flex-row sm:items-center gap-3">
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
                <div className="flex items-center gap-2" role="tablist" aria-label="Filter by sex">
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
                                    : 'text-ink-700 hover:bg-ink-50'
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
                        <thead className="bg-ink-50 text-ink-600 text-2xs uppercase font-semibold tracking-[0.14em]">
                            <tr>
                                <th className="px-5 py-3">Patient</th>
                                <th className="px-5 py-3">Contact</th>
                                <th className="px-5 py-3">Vitals</th>
                                <th className="px-5 py-3">Route to queue</th>
                                <th className="px-5 py-3 text-right">Manage</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-ink-100 text-ink-700">
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
                                        <p className="text-sm font-medium text-ink-700">No patients match the current filters.</p>
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
                                                    <div className={`shrink-0 w-10 h-10 rounded-full flex items-center justify-center text-sm font-semibold ${avatarColor(patient.outpatient_no)}`} aria-hidden="true">
                                                        {initialsOf(patient)}
                                                    </div>
                                                    <div className="min-w-0">
                                                        <div className="font-semibold text-ink-900 truncate">{patient.surname}, {patient.other_names}</div>
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
                                                <div className="flex items-center gap-1.5 text-ink-700">
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
                                                <div className="flex items-center gap-1.5 text-ink-700">
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
                                                <div className="flex flex-wrap gap-1">
                                                    {ROUTE_TARGETS.map(t => {
                                                        const Icon = t.icon;
                                                        const busy = routingId === `${patient.patient_id}:${t.department}`;
                                                        return (
                                                            <button
                                                                key={t.department}
                                                                type="button"
                                                                onClick={() => routePatient(patient, t)}
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
                        <p className="text-sm font-medium text-ink-700">No patients match the current filters.</p>
                    </div>
                ) : (
                    visiblePatients.map(patient => {
                        const age = ageFrom(patient.date_of_birth);
                        const hasAllergies = patient.allergies && patient.allergies.trim();
                        return (
                            <article key={patient.patient_id} className="card p-4">
                                <header className="flex items-start gap-3">
                                    <div className={`shrink-0 w-11 h-11 rounded-full flex items-center justify-center text-sm font-semibold ${avatarColor(patient.outpatient_no)}`} aria-hidden="true">
                                        {initialsOf(patient)}
                                    </div>
                                    <div className="min-w-0 flex-1">
                                        <h3 className="font-semibold text-ink-900 truncate">{patient.surname}, {patient.other_names}</h3>
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
                                        className="shrink-0 w-11 h-11 inline-flex items-center justify-center text-ink-500 hover:text-brand-600 hover:bg-brand-50 rounded-lg cursor-pointer"
                                    >
                                        <MoreVertical size={18} aria-hidden="true" />
                                    </button>
                                </header>

                                <dl className="mt-3 grid grid-cols-2 gap-2 text-xs">
                                    <div>
                                        <dt className="text-ink-500">Phone</dt>
                                        <dd className="text-ink-900 flex items-center gap-1 mt-0.5">
                                            <Phone size={11} className="text-ink-400" aria-hidden="true" />
                                            <span className="truncate">{patient.telephone_1 || '—'}</span>
                                        </dd>
                                    </div>
                                    <div>
                                        <dt className="text-ink-500">Residence</dt>
                                        <dd className="text-ink-900 flex items-center gap-1 mt-0.5">
                                            <MapPin size={11} className="text-ink-400" aria-hidden="true" />
                                            <span className="truncate">{patient.residence || patient.town || '—'}</span>
                                        </dd>
                                    </div>
                                    <div>
                                        <dt className="text-ink-500">Blood</dt>
                                        <dd className="text-ink-900 flex items-center gap-1 mt-0.5">
                                            <Droplet size={11} className="text-rose-500" aria-hidden="true" />
                                            {patient.blood_group && patient.blood_group !== 'Unknown' ? patient.blood_group : 'Unknown'}
                                        </dd>
                                    </div>
                                    <div>
                                        <dt className="text-ink-500">Registered</dt>
                                        <dd className="text-ink-900 mt-0.5" title={patient.registered_on ? new Date(patient.registered_on).toLocaleString() : ''}>
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
                                                    onClick={() => routePatient(patient, t)}
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

                    <div className="relative w-full max-w-4xl bg-white h-full shadow-elevated flex flex-col animate-slide-in-right">
                        <div className="flex items-center justify-between p-6 border-b border-ink-100 bg-white shrink-0">
                            <div>
                                <span className="section-eyebrow">New registration</span>
                                <h2 className="text-xl font-semibold text-ink-900 tracking-tight mt-1 flex items-center gap-2">
                                    <UserPlus className="text-brand-600" size={20} />
                                    Patient registration
                                </h2>
                                <p className="text-sm text-ink-500 mt-1">Complete the form to generate an Outpatient Number.</p>
                            </div>
                            <button onClick={() => setIsModalOpen(false)} aria-label="Close" className="text-ink-400 hover:text-ink-700 p-2 hover:bg-ink-100 rounded-full transition-colors">
                                <X size={20} />
                            </button>
                        </div>

                        <div className="flex-1 overflow-y-auto p-6 bg-ink-50/60 custom-scrollbar">
                            <form id="patientForm" onSubmit={handleSubmit} className="space-y-6">
                                
                                {/* SECTION 1: Identity */}
                                <div className="card p-5 sm:p-6">
                                    <h3 className="section-eyebrow text-brand-700 mb-4 border-b border-ink-100 pb-3 flex items-center gap-2">
                                        <ShieldCheck size={16} /> Identity & Demographics
                                    </h3>
                                    <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                                        <div className="md:col-span-2">
                                            <label className="label">Surname <span className="text-red-500">*</span></label>
                                            <input required type="text" name="surname" value={formData.surname} onChange={handleInputChange} className="input" />
                                        </div>
                                        <div className="md:col-span-2">
                                            <label className="label">Other Names <span className="text-red-500">*</span></label>
                                            <input required type="text" name="other_names" value={formData.other_names} onChange={handleInputChange} className="input" />
                                        </div>
                                        <div>
                                            <label className="label">Sex <span className="text-red-500">*</span></label>
                                            <select name="sex" value={formData.sex} onChange={handleInputChange} className="input">
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
                                            <label className="label">ID Type</label>
                                            <select name="id_type" value={formData.id_type} onChange={handleInputChange} className="input">
                                                <option>National ID</option>
                                                <option>Passport</option>
                                                <option>Birth Certificate</option>
                                                <option>Alien ID</option>
                                            </select>
                                        </div>
                                        <div>
                                            <label className="label">ID Number</label>
                                            <input type="text" name="id_number" value={formData.id_number} onChange={handleInputChange} className="input" />
                                        </div>
                                        <div>
                                            <label className="label">Nationality</label>
                                            <input type="text" name="nationality" value={formData.nationality} onChange={handleInputChange} className="input" />
                                        </div>
                                        <div>
                                            <label className="label">Marital Status</label>
                                            <select name="marital_status" value={formData.marital_status} onChange={handleInputChange} className="input">
                                                <option>Single</option>
                                                <option>Married</option>
                                                <option>Divorced</option>
                                                <option>Widowed</option>
                                            </select>
                                        </div>
                                        <div>
                                            <label className="label">Religion</label>
                                            <input type="text" name="religion" value={formData.religion} onChange={handleInputChange} className="input" />
                                        </div>
                                        <div>
                                            <label className="label">Primary Language</label>
                                            <input type="text" name="primary_language" value={formData.primary_language} onChange={handleInputChange} className="input" />
                                        </div>
                                    </div>
                                </div>

                                {/* SECTION 2: Contact & Location */}
                                <div className="card p-5 sm:p-6">
                                    <h3 className="section-eyebrow text-brand-700 mb-4 border-b border-ink-100 pb-3 flex items-center gap-2">
                                        <MapPin size={16} /> Contact & Location
                                    </h3>
                                    <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                                        <div>
                                            <label className="label">Primary Phone <span className="text-red-500">*</span></label>
                                            <input required type="text" name="telephone_1" value={formData.telephone_1} onChange={handleInputChange} className="input" />
                                        </div>
                                        <div>
                                            <label className="label">Alternative Phone</label>
                                            <input type="text" name="telephone_2" value={formData.telephone_2} onChange={handleInputChange} className="input" />
                                        </div>
                                        <div className="md:col-span-2">
                                            <label className="label">Email Address</label>
                                            <input type="email" name="email" value={formData.email} onChange={handleInputChange} className="input" />
                                        </div>
                                        <div className="md:col-span-2">
                                            <label className="label">Residence (Estate/Area)</label>
                                            <input type="text" name="residence" value={formData.residence} onChange={handleInputChange} className="input" />
                                        </div>
                                        <div>
                                            <label className="label">Town</label>
                                            <input type="text" name="town" value={formData.town} onChange={handleInputChange} className="input" />
                                        </div>
                                        <div>
                                            <label className="label">Postal Address</label>
                                            <input type="text" name="postal_address" value={formData.postal_address} onChange={handleInputChange} className="input" placeholder="P.O Box - Code" />
                                        </div>
                                    </div>
                                </div>

                                {/* SECTION 3: Employment & Next of Kin */}
                                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                                    <div className="card p-5 sm:p-6">
                                        <h3 className="section-eyebrow text-brand-700 mb-4 border-b border-ink-100 pb-3 flex items-center gap-2">
                                            <Briefcase size={16} /> Employment
                                        </h3>
                                        <div className="space-y-4">
                                            <div>
                                                <label className="label">Occupation</label>
                                                <input type="text" name="occupation" value={formData.occupation} onChange={handleInputChange} className="input" />
                                            </div>
                                            <div>
                                                <label className="label">Employer Name</label>
                                                <input type="text" name="employer_name" value={formData.employer_name} onChange={handleInputChange} className="input" />
                                            </div>
                                            <div>
                                                <label className="label">Reference/Staff Number</label>
                                                <input type="text" name="reference_number" value={formData.reference_number} onChange={handleInputChange} className="input" />
                                            </div>
                                        </div>
                                    </div>
                                    <div className="card p-5 sm:p-6">
                                        <h3 className="section-eyebrow text-brand-700 mb-4 border-b border-ink-100 pb-3 flex items-center gap-2">
                                            <Phone size={16} /> Next of Kin
                                        </h3>
                                        <div className="space-y-4">
                                            <div>
                                                <label className="label">NOK Name</label>
                                                <input type="text" name="nok_name" value={formData.nok_name} onChange={handleInputChange} className="input" />
                                            </div>
                                            <div>
                                                <label className="label">Relationship</label>
                                                <input type="text" name="nok_relationship" value={formData.nok_relationship} onChange={handleInputChange} className="input" />
                                            </div>
                                            <div>
                                                <label className="label">NOK Contact Number</label>
                                                <input type="text" name="nok_contact" value={formData.nok_contact} onChange={handleInputChange} className="input" />
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                {/* SECTION 4: Clinical Baselines & Notes */}
                                <div className="card p-5 sm:p-6">
                                    <h3 className="section-eyebrow text-brand-700 mb-4 border-b border-ink-100 pb-3 flex items-center gap-2">
                                        <HeartPulse size={16} /> Clinical Baselines & Notes
                                    </h3>
                                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                        <div>
                                            <label className="label">Blood Group</label>
                                            <select name="blood_group" value={formData.blood_group} onChange={handleInputChange} className="input">
                                                <option>Unknown</option><option>A+</option><option>A-</option>
                                                <option>B+</option><option>B-</option><option>O+</option>
                                                <option>O-</option><option>AB+</option><option>AB-</option>
                                            </select>
                                        </div>
                                        <div className="md:col-span-2">
                                            <label className="label">Known Allergies</label>
                                            <input type="text" name="allergies" value={formData.allergies} onChange={handleInputChange} className="input" placeholder="e.g., Penicillin, Peanuts" />
                                        </div>
                                        <div className="md:col-span-3">
                                            <label className="label">Chronic Conditions</label>
                                            <input type="text" name="chronic_conditions" value={formData.chronic_conditions} onChange={handleInputChange} className="input" placeholder="e.g., Hypertension, Type 2 Diabetes" />
                                        </div>
                                        <div className="md:col-span-3">
                                            <label className="label">Front Desk Notes</label>
                                            <textarea name="notes" value={formData.notes} onChange={handleInputChange} rows="2" className="input" placeholder="Any additional registration remarks..." />
                                        </div>
                                    </div>
                                </div>

                            </form>
                        </div>

                        <div className="p-5 border-t border-ink-100 bg-white flex gap-3 shrink-0">
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
                        onPrint={(p) => { printPatientCard(p); closeDropdown(); }}
                        onExport={exportPatientData}
                        onDeactivate={deactivatePatient}
                        onErase={erasePatient}
                    />
                );
            })()}
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

function RowMenu({ patient, anchorEl, onClose, onView, onPrint, onExport, onDeactivate, onErase }) {
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

    useLayoutEffect(() => { recompute(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [anchorEl]);

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
            className="bg-white rounded-xl shadow-elevated border border-ink-200 py-2 z-[60] text-left animate-fade-in"
        >
            <div className="px-3 pt-1 pb-1.5 text-2xs font-semibold text-ink-500 uppercase tracking-[0.14em]">Manage</div>
            <button type="button" role="menuitem" onClick={() => onView(patient.patient_id)} className="w-full px-3.5 py-2 text-sm text-ink-700 hover:bg-ink-50 flex items-center gap-2.5 cursor-pointer">
                <Eye size={15} className="text-ink-500" aria-hidden="true" /> View history
            </button>
            <button type="button" role="menuitem" onClick={() => onPrint(patient)} className="w-full px-3.5 py-2 text-sm text-ink-700 hover:bg-ink-50 flex items-center gap-2.5 cursor-pointer">
                <Printer size={15} className="text-ink-500" aria-hidden="true" /> Print card
            </button>
            <button type="button" role="menuitem" onClick={() => onExport(patient)} className="w-full px-3.5 py-2 text-sm text-ink-700 hover:bg-ink-50 flex items-center gap-2.5 cursor-pointer">
                <Download size={15} className="text-ink-500" aria-hidden="true" /> Export (KDPA S.26)
            </button>
            <div className="border-t border-ink-100 my-1.5" role="separator" />
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