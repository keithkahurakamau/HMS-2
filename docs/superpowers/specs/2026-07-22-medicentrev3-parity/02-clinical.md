# Module 2 — Clinical (`Clinical`)

Sidebar sub-items: **Registry · Triage · Doctor · Doctor (New) · Special Clinics · Patient Chart · Laboratory · Radiology · Inpatient · Appointments · Referrals**.

Screenshots: `153723–153737` (Registry) · `153818–153840` (Triage) · `153923–153952` (Doctor) · `154026–154108` (Doctor New) · `154123` (Special Clinics grid) · `154143` (Consultation Clinic) · `154240–154307` (Nutrition) · `154330–154357` (Dialysis special-clinic) · `154418` (Patient Chart) · `154444–154506` (Laboratory) · `154612–155146` (Radiology) · `155203–155304` (Inpatient).

HMS-2 refs: `frontend/src/pages/{Patients,Triage,ClinicalDesk,Laboratory,Radiology,Wards,Appointments,MedicalHistory}.jsx`, `backend/app/routes/{clinical,clinical_history,laboratory,radiology,wards,appointments,referrals,triage,queue}.py`, `IcdDiagnosisPicker`, `ReferralModal`, `VitalsTrendsModal`, `PatientHistoryModal`, `VisitHistoryList`.

This is HMS-2's **strongest** area — most core clinical flow exists. Gaps are specialty add-ons + the insurance eligibility edge.

---

## 2.1 Registry — patient registration

**Elements:** `Search for patient by (Name, ID, OP/NO, P/NO, M/S…)`. **Patient Details** form: Surname*, Other Names*, Sex*, Date Of Birth* (+ edit), ID Type, ID Number, Telephone 1*, Telephone 2, Email, Postal Address, Postal Code, Occupation* (+add), Residence*, Town* (+add), Reference Number, Nationality* (+add), Next Of Kin*, Relationship*, Next Of Kin's Contact*, Notes; read-outs Outpatient No / Inpatient No / Registered On; **[Customer Schemes]**, **[+]** save. **[Actions ▾]**: Queue Patient · Deactivate Patient · Delete Patient · Proxied Patients · Update In/Outpatient Pre/Suffixes · **Smart Member Profile** · Import Patients · View Patient Visits · View Visits/Bills History · Files. **View Patients** table (Excel/CSV/Print, Search): Outpatient No, Inpatient No, Surname, Other Names, ID No, Sex.

| Element / capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Full demographic registration + NOK | ✅ Have | `Patients.jsx` | — |
| Customer Schemes (link patient ↔ insurance scheme) | 🟡 Partial | schemes exist; verify patient-scheme linkage UI | P1 |
| **Smart Member Profile** (insurance eligibility/member lookup) | ❌ Missing | can't verify cover before service → revenue risk | P1 |
| Proxied Patients (dependants/next-of-kin billing) | ❌ Missing | — | P3 |
| Import Patients (bulk) | ❌ Missing | — | P3 |
| Update In/Outpatient pre/suffixes (numbering) | ❌ Missing | — | P3 |
| Deactivate / Delete patient | 🟡 Partial | verify soft-delete/deactivate | P3 |

## 2.2 Triage

**Elements:** patient panel + queue. **General Examination** (Vital dropdown, Remark, Units, [+], list). **Systemic Examination** (Body System, Remark, **Is Anomalous** checkbox, [+], list). **Procedures** (Procedure dropdown, [+], list). **Nursing Notes** textarea. **[Save]**. **[Actions ▾]**: Lab Request · Radiology Request · Theatre Request · Queue Patient · Prescription · Visit Summary · Lab Report. Previous-visits table.

| Element / capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Vitals capture + units + anomalous flag | ✅ Have | `Triage.jsx` | — |
| Systemic exam by body system | 🟡 Partial | verify structured body-system list | P3 |
| Nursing notes + procedures | ✅ Have | | — |

## 2.3 Doctor & 2.4 Doctor (New) — consultation

**Doctor (classic):** Doctor's Panel — Complaints (+), History of Presenting Illness (textarea+Save), Medical/Surgical/Family/Social/Economic History (+ each), Allergies (+), Impressions (+), Diagnosis (Enter diagnosis / **Select ICD-10 from list**, +), Clinical Summary. "Patients Queued to Consultation Rooms" modal (Queue No/OPD No/Name/From/To/Mins, double-click select, View All Patients). Previous-visits table (Visit Id/Date/Note/Summary Report).

**Doctor (New) = DoctorV2:** tabbed **Encounter Notes** (Complaints, HPI, Physical Examination, Impressions, Diagnosis ICD-10, Clinical Summary — each Save) + **Patient History** (Medical/Surgical/Family/Social/Economic/Allergies).

**[Actions ▾] (the mega-menu, shared across clinical):** Refer Patient · Vitals · Physical Examination · Lab Request · Radiology Request · **Theatre Request** · Appointment · My Appointments · Diagnosis · Assess & Plan · Prescription · **Optical Prescription** · Queue Patient · Billing · **Sick Note** · **Consent Form** · **Order Sets** · Pick Patient In Admission · Files · **External Request Form** · Admit Patient · Special Clinic Summary · Visit Summary · Lab Report · Lab Report (Test Per Page) · Theatre Report · Examination Report · All Visits Report · **Blood Pressure Trend**.

| Element / capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Consultation workspace (complaints/HPI/histories/summary) | ✅ Have | `ClinicalDesk.jsx` + inline draft safety-net | — |
| ICD-10 diagnosis picker (+ custom) | ✅ Have | `IcdDiagnosisPicker` | — |
| Encounter / Patient-History tabs | ✅ Have | | — |
| Queue-to-room modal + previous visits | ✅ Have | `queue.py`, `VisitHistoryList` | — |
| Refer patient (+ referral letter) | ✅ Have | `ReferralModal`, referral letters | — |
| Prescription | ✅ Have | `Pharmacy.jsx` link | — |
| Blood Pressure Trend | ✅ Have | `VitalsTrendsModal` | — |
| **Physical Examination** (structured) | 🟡 Partial | free-text yes; structured template? | P2 |
| **Assess & Plan** (structured SOAP-P) | 🟡 Partial | verify plan section | P2 |
| **Optical Prescription** (eye Rx: sphere/cyl/axis) | ❌ Missing | needed for eye clinics | P2 |
| **Order Sets** (bundled orders) | ❌ Missing | clinical efficiency/safety | P2 |
| **Sick Note** (medical certificate) | ❌ Missing | common OPD deliverable | P2 |
| **Consent Form** (procedure consent PDF) | 🟡 Partial | data-consent util exists; clinical procedure consent ❌ | P2 |
| **External Request Form** (refer test to outside lab) | ❌ Missing | — | P2 |
| Files/attachments per visit | 🟡 Partial | verify per-visit uploads | P3 |

## 2.5 Special Clinics

**Elements:** card grid of sub-clinics — **Consultation Clinic**, **Nutrition**, **Dialysis**. Nutrition form: Anthropometrics Assessment, Biochemical Assessment, Clinical Assessment, 24 Hr Recall, Economic Status, Functional Assessment, Nutrition Counselling, Monitoring and Evaluation (+ Save). Each clinic has the shared Actions menu + "Special Clinic Summary".

| Element / capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Special-clinic framework (typed sub-clinics) | ❌ Missing | no clinic-type routing | P2 |
| **Nutrition / dietetics assessment** | ❌ Missing | full ADIME-style form absent | P2 |

## 2.6 Patient Chart — unified EMR view

**Elements:** Patient Info (Surname/Othernames/Gender/Age/OPD No/Occupation/Telephone/Residence); **[Edit Patient] [New Patient] [My Queue]**. **Visits** with **[New Visit]** + tabbed: **Vitals · Encounter · Notes · Clinics · Requests · Prescription · Appointments · Insurance · Reports · More▾**. Vitals tab: Vital Signs (+), Body Systems (+), Procedures (+), Nursing Notes (edit).

| Element / capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Unified tabbed patient chart across all visit data | 🟡 Partial | `PatientHistoryModal` + `VisitHistoryList` cover pieces; no single tabbed chart w/ Insurance/Requests/Prescription tabs | P2 |

## 2.7 Laboratory

**Elements:** patient panel + queue. Requested Tests and Results — Patient Scheme dropdown, Lab Test dropdown (+), request list; Test/Specimen read-outs, **[Sample Collection] [Test Conclusion]**, results table (Component, Lower, Upper, Units, Value, Result, **Anom**, Clear). **[Actions ▾]**: View Requests · View Previous Visits · Queue Patient · **Approve Lab Results** · Files · Lab Request Slip · Visit Summary · Lab Report · Lab Report (Test Per Page) · **Unlock Lab Request**.

| Element / capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Lab requests, specimens, results, reference ranges | ✅ Have | `laboratory.py` + `Laboratory.jsx` | — |
| Sample collection → test conclusion → approve results | ✅ Have | verify approve/lock states | — |
| Lab request slip / test-per-page report | 🟡 Partial | verify print variants | P3 |

## 2.8 Radiology

**Elements:** Radiology - Examination — Requested Examination(s) list; Examination: History / Technique-Procedure / Findings; Impression / Comment / Examiner / Radiologist; Centre; Date Time Done; Reason (if not done); **Is Done** / **Is Internal** checkboxes; Save. **[Actions ▾]**: Create Radiology Request · View Radiology Requests · **View Images** · Queue Patient · Files · Unlock Selected Examination · Examination Report.

| Element / capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Radiology requests + structured report | ✅ Have | `radiology.py` + `Radiology.jsx` | — |
| Internal vs external radiologist / centre | 🟡 Partial | verify external centre + examiner fields | P3 |
| **View Images (PACS/DICOM)** | 🟡 Partial | some image handling; no PACS viewer | P3 |

## 2.9 Inpatient — admissions & discharge

**Elements:** Admission Details — Patient Admission (Adm ID, Othernames, OP NO, Ward, Rate/day, Admitted By, Adm DateTime, Discharged By, Visit ID, Surname, IP NO, Ref No, Bed No, Bed Status, Doctor, Duration), **[Admit From Queue]**. Discharge Patient (Discharged checkbox, **Discharge Status** = Alive / Absconded / Dead, Discharging Doctor, Discharge In, Backdate Discharge Date + datetime). **Gate Pass**: [Generate Gatepass] [View Gatepass]. Admissions table (IPD No, OPD No, Patient, Admitted On, Duration, Ward, Bed, Scheme, Bill; Excel/CSV/Print; Search); filters View (Currently in Admission), Ward, From/To; legend Dead/Alive/Absconded. _(Note: a "pay for Theatre Module first" toast confirms per-module licensing over there.)_

| Element / capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Ward/bed admissions register | ✅ Have | `Wards.jsx` + `wards.py` | — |
| Admit-from-queue | ✅ Have | | — |
| Discharge w/ status (Alive/Absconded/**Dead**) + discharging doctor | 🟡 Partial | verify discharge-status enum + mortality flag | P2 |
| Per-day rate → running bill | 🟡 Partial | verify bed-day auto-billing | P1 |
| **Generate/View Gate Pass on discharge** | ❌ Missing | ties to Billing §1.6 | P2 |

## 2.10 Appointments

**Elements:** Patient Details (Appointment No, Surname, Outpatient No, Other Names, Telephone, Email). **Appointment Schedule** (Date Time, Doctor, Purpose). **Appointment Status** (Seen By, Comment, **Has Been Seen** checkbox, [Update]). Month **calendar** widget (prev/next nav, day grid). **[Actions ▾]**: Book Appointment. **View: Appointments** table (Appointment No, Outpatient No, Surname, Other Names, Doctor, Date Time; Excel/CSV/Print; Search).

## 2.11 Referrals

**Elements:** patient panel + **[View Referral Report]**. **Referral Details**: Referral Type, Referred From, Referred To, Referring Doctor, Reason For Referral, Date Time Referred, Date Time Received, Received By, Complaints, General Examinations, System Examinations, Investigations, Other Examinations, Prescription; **[Update]**. **Referrals View** table (No, Referred From, Referred To, Referring Doctor, DateTime Referred, DateTime Received, Reason).

| Element / capability | HMS-2 | Gap notes | Pri |
|---|---|---|---|
| Appointments (schedule/status/seen-by + calendar) | ✅ Have | `Appointments.jsx` + `appointments.py` + `Calendar.jsx` | — |
| Referrals (type/from/to/structured exams/prescription + letter) | ✅ Have | `referrals.py` + `ReferralModal` + referral letters | — |

---

## Clinical summary

Core OPD/IPD clinical flow is **largely at parity** (registry, triage, consultation w/ ICD-10, lab, radiology, admissions, appointments, referrals). The real gaps are **specialty & compliance add-ons** plus one revenue item:

- ❌ **Theatre / Surgery module** (operative notes, theatre scheduling, theatre report) — **P1** (clinical + revenue; sold separately by MedicentreV3)
- ❌ **Smart Member Profile / insurance eligibility check** — **P1** (verify cover before service)
- ❌ **Nutrition clinic + Special-Clinics framework** — P2
- ❌ **Order Sets, Sick Note, Optical Prescription, External Request Form, clinical Consent Form** — P2
- 🟡 **Unified Patient Chart**, **discharge-status/mortality**, **bed-day auto-billing**, **gate pass** — P1–P2
