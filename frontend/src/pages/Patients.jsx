import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../api/client';
import toast from 'react-hot-toast';
import {
    Search, UserPlus, X, Activity, Clock, ShieldCheck, Users,
    MapPin, Phone, Briefcase, HeartPulse, FileText,
    MoreVertical, Stethoscope, TestTube, AlertCircle, UserMinus,
    Pill, Bed, CreditCard, Printer, Download, Trash
} from 'lucide-react';
import { printPatientCard } from '../utils/printTemplates';
import PageHeader from '../components/PageHeader';

export default function Patients() {
    const [patients, setPatients] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [searchQuery, setSearchQuery] = useState('');
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [isSubmitting, setIsSubmitting] = useState(false);

    // Interactive States
    const [activeDropdown, setActiveDropdown] = useState(null);
    const navigate = useNavigate();

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
            const response = await apiClient.get(`/patients/?search=${searchQuery}`);
            setPatients(response.data);
        } catch (error) {
            toast.error("Failed to load patients. Are you authorized?");
        } finally {
            setIsLoading(false);
        }
    };

    const handleInputChange = (e) => {
        setFormData({ ...formData, [e.target.name]: e.target.value });
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
    const routePatient = async (patientId, department) => {
        try {
            await apiClient.post(`/patients/${patientId}/route`, { department, acuity_level: 3 });
            toast.success(`Successfully sent to ${department} queue.`);
            setActiveDropdown(null);
        } catch (error) {
            toast.error(error.response?.data?.detail || `Failed to route to ${department}`);
        }
    };

    // --- Action: View History ---
    const viewHistory = (patientId) => {
        setActiveDropdown(null);
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

    return (
        <div className="space-y-6 relative h-full">
            <PageHeader
                eyebrow="Front desk"
                icon={Users}
                title="Patient Directory"
                subtitle="Manage comprehensive registrations, medical records, and departmental queues."
                actions={
                    <button onClick={() => setIsModalOpen(true)} className="btn-primary cursor-pointer">
                        <UserPlus size={16} /> Register patient
                    </button>
                }
            />

            {/* Toolbar */}
            <div className="card p-3 sm:p-4 flex items-center justify-between">
                <div className="relative w-full max-w-md">
                    <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" />
                    <input
                        type="text"
                        placeholder="Search by OP Number, name, ID, or phone…"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        className="input pl-10"
                    />
                </div>
            </div>

            {/* Data Table */}
            <div className="card overflow-visible">
                <div className="overflow-x-auto overflow-y-visible pb-24">
                    <table className="table-clean">
                        <thead>
                            <tr>
                                <th>OP Number</th>
                                <th>Patient Profile</th>
                                <th>Contact Info</th>
                                <th>Registered Date</th>
                                <th className="text-center">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {isLoading ? (
                                <tr>
                                    <td colSpan="5" className="px-6 py-12 text-center text-ink-400">
                                        <Activity className="animate-spin mx-auto mb-2 text-brand-500" size={22} />
                                        Loading patient records…
                                    </td>
                                </tr>
                            ) : patients.length === 0 ? (
                                <tr>
                                    <td colSpan="5" className="px-6 py-12 text-center text-ink-400">
                                        No active patients found matching your search.
                                    </td>
                                </tr>
                            ) : (
                                patients.map((patient) => (
                                    <tr key={patient.patient_id}>
                                        <td className="font-mono text-xs font-semibold text-brand-700">
                                            {patient.outpatient_no}
                                        </td>
                                        <td>
                                            <div className="font-semibold text-ink-900">
                                                {patient.surname}, {patient.other_names}
                                            </div>
                                            <div className="text-xs text-ink-500 mt-0.5">
                                                {patient.sex} &middot; {patient.date_of_birth}
                                            </div>
                                        </td>
                                        <td>
                                            <div className="flex items-center gap-1.5 text-ink-700"><Phone size={12} className="text-ink-400" /> {patient.telephone_1}</div>
                                            <div className="text-xs text-ink-500 mt-0.5 flex items-center gap-1.5">
                                                <MapPin size={12} className="text-ink-400" /> {patient.residence || patient.town || 'Unspecified'}
                                            </div>
                                        </td>
                                        <td className="text-ink-500 text-xs">
                                            {new Date(patient.registered_on).toLocaleDateString()}
                                        </td>
                                        <td className="px-6 py-4 text-center relative">
                                            <button
                                                onClick={() => setActiveDropdown(activeDropdown === patient.patient_id ? null : patient.patient_id)}
                                                aria-label="Patient actions"
                                                className="p-2 text-ink-400 hover:text-brand-600 hover:bg-brand-50 rounded-lg transition-colors"
                                            >
                                                <MoreVertical size={16} />
                                            </button>

                                            {activeDropdown === patient.patient_id && (
                                                <div className="absolute right-10 top-10 w-52 bg-white rounded-xl shadow-elevated border border-ink-200/70 py-2 z-30 text-left animate-fade-in">
                                                    <div className="px-3 pt-1 pb-1.5 text-2xs font-semibold text-ink-400 uppercase tracking-[0.14em]">Route to</div>
                                                    <button onClick={() => routePatient(patient.patient_id, 'Clinical Desk')} className="w-full px-3.5 py-2 text-sm text-ink-700 hover:bg-ink-50 flex items-center gap-2.5"><Stethoscope size={15} className="text-blue-500" /> Clinical Desk</button>
                                                    <button onClick={() => routePatient(patient.patient_id, 'Laboratory')} className="w-full px-3.5 py-2 text-sm text-ink-700 hover:bg-ink-50 flex items-center gap-2.5"><TestTube size={15} className="text-purple-500" /> Laboratory</button>
                                                    <button onClick={() => routePatient(patient.patient_id, 'Radiology')} className="w-full px-3.5 py-2 text-sm text-ink-700 hover:bg-ink-50 flex items-center gap-2.5"><Activity size={15} className="text-indigo-500" /> Radiology</button>
                                                    <button onClick={() => routePatient(patient.patient_id, 'Pharmacy')} className="w-full px-3.5 py-2 text-sm text-ink-700 hover:bg-ink-50 flex items-center gap-2.5"><Pill size={15} className="text-accent-600" /> Pharmacy</button>
                                                    <button onClick={() => routePatient(patient.patient_id, 'Billing')} className="w-full px-3.5 py-2 text-sm text-ink-700 hover:bg-ink-50 flex items-center gap-2.5"><CreditCard size={15} className="text-amber-500" /> Billing</button>
                                                    <button onClick={() => routePatient(patient.patient_id, 'Wards')} className="w-full px-3.5 py-2 text-sm text-ink-700 hover:bg-ink-50 flex items-center gap-2.5"><Bed size={15} className="text-rose-500" /> Wards</button>

                                                    <div className="border-t border-ink-100 my-1.5"></div>
                                                    <div className="px-3 pt-1 pb-1.5 text-2xs font-semibold text-ink-400 uppercase tracking-[0.14em]">Manage</div>

                                                    <button onClick={() => viewHistory(patient.patient_id)} className="w-full px-3.5 py-2 text-sm text-ink-700 hover:bg-ink-50 flex items-center gap-2.5"><Clock size={15} className="text-ink-500" /> View History</button>
                                                    <button onClick={() => { printPatientCard(patient); setActiveDropdown(null); }} className="w-full px-3.5 py-2 text-sm text-ink-700 hover:bg-ink-50 flex items-center gap-2.5"><Printer size={15} className="text-ink-500" /> Print Card</button>
                                                    <button onClick={() => exportPatientData(patient)} className="w-full px-3.5 py-2 text-sm text-ink-700 hover:bg-ink-50 flex items-center gap-2.5"><Download size={15} className="text-ink-500" /> Export Data (KDPA)</button>
                                                    <button onClick={() => deactivatePatient(patient.patient_id)} className="w-full px-3.5 py-2 text-sm text-rose-600 hover:bg-rose-50 flex items-center gap-2.5"><UserMinus size={15} /> Deactivate</button>
                                                    <button onClick={() => erasePatient(patient)} className="w-full px-3.5 py-2 text-sm text-rose-700 hover:bg-rose-50 flex items-center gap-2.5 font-semibold"><Trash size={15} /> Erase (KDPA S.40)</button>
                                                </div>
                                            )}
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
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
                                            <label className="label">Date of Birth <span className="text-red-500">*</span></label>
                                            <input required type="date" name="date_of_birth" value={formData.date_of_birth} onChange={handleInputChange} className="input" />
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
        </div>
    );
}