import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../api/client';
import toast from 'react-hot-toast';
import { 
    Search, UserPlus, X, Activity, Clock, ShieldCheck, 
    MapPin, Phone, Briefcase, HeartPulse, FileText, 
    MoreVertical, Stethoscope, TestTube, AlertCircle, UserMinus,
    Pill, Bed, CreditCard
} from 'lucide-react';

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
        navigate(`/medical-history?patient_id=${patientId}`);
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

    return (
        <div className="space-y-6 relative h-full">
            {/* Page Header */}
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Patient Directory</h1>
                    <p className="text-sm text-slate-500 mt-1">Manage comprehensive registrations, medical records, and departmental queues.</p>
                </div>
                <button 
                    onClick={() => setIsModalOpen(true)}
                    className="inline-flex items-center gap-2 bg-brand-600 hover:bg-brand-700 text-white px-4 py-2.5 rounded-lg text-sm font-medium transition-colors shadow-sm"
                >
                    <UserPlus size={18} />
                    Register New Patient
                </button>
            </div>

            {/* Toolbar */}
            <div className="bg-white p-4 rounded-xl shadow-soft border border-slate-100 flex items-center justify-between">
                <div className="relative w-full max-w-md">
                    <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                    <input 
                        type="text" 
                        placeholder="Search by OP Number, Name, ID, or Phone..." 
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        className="w-full pl-10 pr-4 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500 text-sm transition-all"
                    />
                </div>
            </div>

            {/* Data Table */}
            <div className="bg-white rounded-xl shadow-soft border border-slate-100 overflow-visible">
                <div className="overflow-x-auto overflow-y-visible pb-24">
                    <table className="w-full text-left text-sm text-slate-600">
                        <thead className="bg-slate-50 text-slate-500 text-xs uppercase font-semibold border-b border-slate-200">
                            <tr>
                                <th className="px-6 py-4">OP Number</th>
                                <th className="px-6 py-4">Patient Profile</th>
                                <th className="px-6 py-4">Contact Info</th>
                                <th className="px-6 py-4">Registered Date</th>
                                <th className="px-6 py-4 text-center">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                            {isLoading ? (
                                <tr>
                                    <td colSpan="5" className="px-6 py-12 text-center text-slate-400">
                                        <Activity className="animate-spin mx-auto mb-2 text-brand-500" size={24} />
                                        Loading patient records...
                                    </td>
                                </tr>
                            ) : patients.length === 0 ? (
                                <tr>
                                    <td colSpan="5" className="px-6 py-12 text-center text-slate-400">
                                        No active patients found matching your search.
                                    </td>
                                </tr>
                            ) : (
                                patients.map((patient) => (
                                    <tr key={patient.patient_id} className="hover:bg-slate-50/50 transition-colors">
                                        <td className="px-6 py-4 font-medium text-brand-700">
                                            {patient.outpatient_no}
                                        </td>
                                        <td className="px-6 py-4">
                                            <div className="font-semibold text-slate-900">
                                                {patient.surname}, {patient.other_names}
                                            </div>
                                            <div className="text-xs text-slate-500 mt-0.5">
                                                {patient.sex} • {patient.date_of_birth}
                                            </div>
                                        </td>
                                        <td className="px-6 py-4">
                                            <div className="flex items-center gap-1"><Phone size={12}/> {patient.telephone_1}</div>
                                            <div className="text-xs text-slate-500 mt-0.5 flex items-center gap-1">
                                                <MapPin size={12}/> {patient.residence || patient.town || 'Unspecified'}
                                            </div>
                                        </td>
                                        <td className="px-6 py-4 text-slate-500">
                                            {new Date(patient.registered_on).toLocaleDateString()}
                                        </td>
                                        <td 
                                            className="px-6 py-4 text-center relative"
                                            onMouseLeave={() => setActiveDropdown(null)}
                                        >
                                            {/* Action Dropdown Trigger */}
                                            <button 
                                                onMouseEnter={() => setActiveDropdown(patient.patient_id)}
                                                className="p-2 text-slate-400 hover:text-brand-600 hover:bg-brand-50 rounded-lg transition-colors"
                                            >
                                                <MoreVertical size={18} />
                                            </button>

                                            {/* Dropdown Menu */}
                                            {activeDropdown === patient.patient_id && (
                                                <div className="absolute right-10 top-10 w-48 bg-white rounded-xl shadow-lg border border-slate-200 py-2 z-20 text-left">
                                                    <div className="px-3 py-1 text-xs font-semibold text-slate-400 uppercase tracking-wider">Route To</div>
                                                    <button onClick={() => routePatient(patient.patient_id, 'Clinical Desk')} className="w-full px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 flex items-center gap-2">
                                                        <Stethoscope size={16} className="text-blue-500" /> Clinical Desk
                                                    </button>
                                                    <button onClick={() => routePatient(patient.patient_id, 'Laboratory')} className="w-full px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 flex items-center gap-2">
                                                        <TestTube size={16} className="text-purple-500" /> Laboratory
                                                    </button>
                                                    <button onClick={() => routePatient(patient.patient_id, 'Radiology')} className="w-full px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 flex items-center gap-2">
                                                        <Activity size={16} className="text-indigo-500" /> Radiology
                                                    </button>
                                                    <button onClick={() => routePatient(patient.patient_id, 'Pharmacy')} className="w-full px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 flex items-center gap-2">
                                                        <Pill size={16} className="text-emerald-500" /> Pharmacy
                                                    </button>
                                                    <button onClick={() => routePatient(patient.patient_id, 'Billing')} className="w-full px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 flex items-center gap-2">
                                                        <CreditCard size={16} className="text-amber-500" /> Billing
                                                    </button>
                                                    <button onClick={() => routePatient(patient.patient_id, 'Wards')} className="w-full px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 flex items-center gap-2">
                                                        <Bed size={16} className="text-rose-500" /> Wards
                                                    </button>
                                                    
                                                    <div className="border-t border-slate-100 my-1"></div>
                                                    <div className="px-3 py-1 text-xs font-semibold text-slate-400 uppercase tracking-wider">Manage</div>
                                                    
                                                    <button onClick={() => viewHistory(patient.patient_id)} className="w-full px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 flex items-center gap-2">
                                                        <Clock size={16} className="text-slate-500" /> View History
                                                    </button>
                                                    <button onClick={() => deactivatePatient(patient.patient_id)} className="w-full px-4 py-2 text-sm text-red-600 hover:bg-red-50 flex items-center gap-2">
                                                        <UserMinus size={16} /> Deactivate
                                                    </button>
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
                    <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm transition-opacity" onClick={() => setIsModalOpen(false)}></div>
                    
                    <div className="relative w-full max-w-4xl bg-white h-full shadow-2xl flex flex-col animate-in slide-in-from-right">
                        <div className="flex items-center justify-between p-6 border-b border-slate-100 bg-slate-50 shrink-0">
                            <div>
                                <h2 className="text-xl font-bold text-slate-900 flex items-center gap-2">
                                    <UserPlus className="text-brand-600" size={24} />
                                    Enterprise Patient Registration
                                </h2>
                                <p className="text-sm text-slate-500 mt-1">Complete comprehensive data entry to generate Outpatient Number.</p>
                            </div>
                            <button onClick={() => setIsModalOpen(false)} className="text-slate-400 hover:text-slate-600 p-2 hover:bg-slate-200 rounded-full transition-colors">
                                <X size={24} />
                            </button>
                        </div>

                        <div className="flex-1 overflow-y-auto p-6 bg-slate-50/50">
                            <form id="patientForm" onSubmit={handleSubmit} className="space-y-8">
                                
                                {/* SECTION 1: Identity */}
                                <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
                                    <h3 className="text-sm font-bold text-brand-700 uppercase tracking-wider mb-4 border-b border-brand-100 pb-2 flex items-center gap-2">
                                        <ShieldCheck size={16} /> Identity & Demographics
                                    </h3>
                                    <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                                        <div className="md:col-span-2">
                                            <label className="block text-xs font-semibold text-slate-600 mb-1">Surname <span className="text-red-500">*</span></label>
                                            <input required type="text" name="surname" value={formData.surname} onChange={handleInputChange} className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none" />
                                        </div>
                                        <div className="md:col-span-2">
                                            <label className="block text-xs font-semibold text-slate-600 mb-1">Other Names <span className="text-red-500">*</span></label>
                                            <input required type="text" name="other_names" value={formData.other_names} onChange={handleInputChange} className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none" />
                                        </div>
                                        <div>
                                            <label className="block text-xs font-semibold text-slate-600 mb-1">Sex <span className="text-red-500">*</span></label>
                                            <select name="sex" value={formData.sex} onChange={handleInputChange} className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none bg-white">
                                                <option>Male</option>
                                                <option>Female</option>
                                            </select>
                                        </div>
                                        <div>
                                            <label className="block text-xs font-semibold text-slate-600 mb-1">Date of Birth <span className="text-red-500">*</span></label>
                                            <input required type="date" name="date_of_birth" value={formData.date_of_birth} onChange={handleInputChange} className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none" />
                                        </div>
                                        <div>
                                            <label className="block text-xs font-semibold text-slate-600 mb-1">ID Type</label>
                                            <select name="id_type" value={formData.id_type} onChange={handleInputChange} className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none bg-white">
                                                <option>National ID</option>
                                                <option>Passport</option>
                                                <option>Birth Certificate</option>
                                                <option>Alien ID</option>
                                            </select>
                                        </div>
                                        <div>
                                            <label className="block text-xs font-semibold text-slate-600 mb-1">ID Number</label>
                                            <input type="text" name="id_number" value={formData.id_number} onChange={handleInputChange} className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none" />
                                        </div>
                                        <div>
                                            <label className="block text-xs font-semibold text-slate-600 mb-1">Nationality</label>
                                            <input type="text" name="nationality" value={formData.nationality} onChange={handleInputChange} className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none" />
                                        </div>
                                        <div>
                                            <label className="block text-xs font-semibold text-slate-600 mb-1">Marital Status</label>
                                            <select name="marital_status" value={formData.marital_status} onChange={handleInputChange} className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none bg-white">
                                                <option>Single</option>
                                                <option>Married</option>
                                                <option>Divorced</option>
                                                <option>Widowed</option>
                                            </select>
                                        </div>
                                        <div>
                                            <label className="block text-xs font-semibold text-slate-600 mb-1">Religion</label>
                                            <input type="text" name="religion" value={formData.religion} onChange={handleInputChange} className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none" />
                                        </div>
                                        <div>
                                            <label className="block text-xs font-semibold text-slate-600 mb-1">Primary Language</label>
                                            <input type="text" name="primary_language" value={formData.primary_language} onChange={handleInputChange} className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none" />
                                        </div>
                                    </div>
                                </div>

                                {/* SECTION 2: Contact & Location */}
                                <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
                                    <h3 className="text-sm font-bold text-brand-700 uppercase tracking-wider mb-4 border-b border-brand-100 pb-2 flex items-center gap-2">
                                        <MapPin size={16} /> Contact & Location
                                    </h3>
                                    <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                                        <div>
                                            <label className="block text-xs font-semibold text-slate-600 mb-1">Primary Phone <span className="text-red-500">*</span></label>
                                            <input required type="text" name="telephone_1" value={formData.telephone_1} onChange={handleInputChange} className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none" />
                                        </div>
                                        <div>
                                            <label className="block text-xs font-semibold text-slate-600 mb-1">Alternative Phone</label>
                                            <input type="text" name="telephone_2" value={formData.telephone_2} onChange={handleInputChange} className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none" />
                                        </div>
                                        <div className="md:col-span-2">
                                            <label className="block text-xs font-semibold text-slate-600 mb-1">Email Address</label>
                                            <input type="email" name="email" value={formData.email} onChange={handleInputChange} className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none" />
                                        </div>
                                        <div className="md:col-span-2">
                                            <label className="block text-xs font-semibold text-slate-600 mb-1">Residence (Estate/Area)</label>
                                            <input type="text" name="residence" value={formData.residence} onChange={handleInputChange} className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none" />
                                        </div>
                                        <div>
                                            <label className="block text-xs font-semibold text-slate-600 mb-1">Town</label>
                                            <input type="text" name="town" value={formData.town} onChange={handleInputChange} className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none" />
                                        </div>
                                        <div>
                                            <label className="block text-xs font-semibold text-slate-600 mb-1">Postal Address</label>
                                            <input type="text" name="postal_address" value={formData.postal_address} onChange={handleInputChange} className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none" placeholder="P.O Box - Code" />
                                        </div>
                                    </div>
                                </div>

                                {/* SECTION 3: Employment & Next of Kin */}
                                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                                    <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
                                        <h3 className="text-sm font-bold text-brand-700 uppercase tracking-wider mb-4 border-b border-brand-100 pb-2 flex items-center gap-2">
                                            <Briefcase size={16} /> Employment
                                        </h3>
                                        <div className="space-y-4">
                                            <div>
                                                <label className="block text-xs font-semibold text-slate-600 mb-1">Occupation</label>
                                                <input type="text" name="occupation" value={formData.occupation} onChange={handleInputChange} className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none" />
                                            </div>
                                            <div>
                                                <label className="block text-xs font-semibold text-slate-600 mb-1">Employer Name</label>
                                                <input type="text" name="employer_name" value={formData.employer_name} onChange={handleInputChange} className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none" />
                                            </div>
                                            <div>
                                                <label className="block text-xs font-semibold text-slate-600 mb-1">Reference/Staff Number</label>
                                                <input type="text" name="reference_number" value={formData.reference_number} onChange={handleInputChange} className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none" />
                                            </div>
                                        </div>
                                    </div>
                                    <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
                                        <h3 className="text-sm font-bold text-brand-700 uppercase tracking-wider mb-4 border-b border-brand-100 pb-2 flex items-center gap-2">
                                            <Phone size={16} /> Next of Kin
                                        </h3>
                                        <div className="space-y-4">
                                            <div>
                                                <label className="block text-xs font-semibold text-slate-600 mb-1">NOK Name</label>
                                                <input type="text" name="nok_name" value={formData.nok_name} onChange={handleInputChange} className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none" />
                                            </div>
                                            <div>
                                                <label className="block text-xs font-semibold text-slate-600 mb-1">Relationship</label>
                                                <input type="text" name="nok_relationship" value={formData.nok_relationship} onChange={handleInputChange} className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none" />
                                            </div>
                                            <div>
                                                <label className="block text-xs font-semibold text-slate-600 mb-1">NOK Contact Number</label>
                                                <input type="text" name="nok_contact" value={formData.nok_contact} onChange={handleInputChange} className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none" />
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                {/* SECTION 4: Clinical Baselines & Notes */}
                                <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
                                    <h3 className="text-sm font-bold text-brand-700 uppercase tracking-wider mb-4 border-b border-brand-100 pb-2 flex items-center gap-2">
                                        <HeartPulse size={16} /> Clinical Baselines & Notes
                                    </h3>
                                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                        <div>
                                            <label className="block text-xs font-semibold text-slate-600 mb-1">Blood Group</label>
                                            <select name="blood_group" value={formData.blood_group} onChange={handleInputChange} className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none bg-white">
                                                <option>Unknown</option><option>A+</option><option>A-</option>
                                                <option>B+</option><option>B-</option><option>O+</option>
                                                <option>O-</option><option>AB+</option><option>AB-</option>
                                            </select>
                                        </div>
                                        <div className="md:col-span-2">
                                            <label className="block text-xs font-semibold text-slate-600 mb-1">Known Allergies</label>
                                            <input type="text" name="allergies" value={formData.allergies} onChange={handleInputChange} className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none" placeholder="e.g., Penicillin, Peanuts" />
                                        </div>
                                        <div className="md:col-span-3">
                                            <label className="block text-xs font-semibold text-slate-600 mb-1">Chronic Conditions</label>
                                            <input type="text" name="chronic_conditions" value={formData.chronic_conditions} onChange={handleInputChange} className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none" placeholder="e.g., Hypertension, Type 2 Diabetes" />
                                        </div>
                                        <div className="md:col-span-3">
                                            <label className="block text-xs font-semibold text-slate-600 mb-1">Front Desk Notes</label>
                                            <textarea name="notes" value={formData.notes} onChange={handleInputChange} rows="2" className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none" placeholder="Any additional registration remarks..." />
                                        </div>
                                    </div>
                                </div>

                            </form>
                        </div>

                        <div className="p-6 border-t border-slate-200 bg-white flex gap-4 shrink-0 shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.05)]">
                            <button 
                                type="button"
                                onClick={() => setIsModalOpen(false)}
                                className="px-6 py-2.5 border border-slate-300 text-slate-700 rounded-lg font-medium hover:bg-slate-50 transition-colors"
                            >
                                Cancel
                            </button>
                            <button 
                                type="submit" 
                                form="patientForm"
                                disabled={isSubmitting}
                                className="flex-1 bg-brand-600 hover:bg-brand-700 text-white py-2.5 rounded-lg font-medium transition-colors disabled:opacity-50 shadow-md flex items-center justify-center gap-2"
                            >
                                {isSubmitting ? (
                                    <><Activity className="animate-spin" size={18} /> Processing to Database...</>
                                ) : (
                                    'Register Patient & Generate Outpatient Number'
                                )}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}