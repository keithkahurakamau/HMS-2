# MEDIFLEET COOKIE AND SESSION TOKEN POLICY

---

## [HOSPITAL NAME]
**System:** MediFleet Hospital Management System
**Address:** [FILL IN — Street, City, County, Kenya]
**Tel:** [FILL IN]
**Email:** [FILL IN]
**Data Protection Officer:** [FILL IN — Name, Email, Phone]
**Policy Effective Date:** [FILL IN — DD/MM/YYYY]
**Reference No:** [REF-CKPOL-YYYY]

---

## LEGAL BASIS

This Cookie and Session Policy is issued pursuant to Section 25 of the Kenya Data Protection Act 2019 (KDPA 2019), which requires data controllers to inform data subjects about the collection and processing of their personal data. Session tokens and cookies used by MediFleet constitute the processing of personal data to the extent they are associated with an identifiable individual user.

This policy applies to:
- All hospital staff members who access the MediFleet Hospital Management System via any web browser.
- All patients and authorised representatives accessing the MediFleet Patient Portal.

---

## 1. WHAT ARE COOKIES AND SESSION TOKENS?

A **cookie** is a small text file placed on your device (computer, tablet, or smartphone) by a website or web application when you visit it. Cookies allow the application to remember information about your session or preferences.

A **session token** is a temporary security credential issued by MediFleet to verify your identity during an active session. Session tokens are typically stored in cookies or in the browser's local storage.

MediFleet does **not** use third-party advertising cookies, analytics trackers, or social media pixels. All cookies set by MediFleet are strictly necessary for the secure and functional operation of the system.

---

## 2. COOKIES SET BY MEDIFLEET

The following cookies and session tokens are set by the MediFleet Hospital Management System:

---

### 2.1 `access_token`

| Attribute | Detail |
|---|---|
| **Name** | `access_token` |
| **Purpose** | Authenticates the user's identity for each request made during an active MediFleet session. This token is verified server-side on every API call to confirm the user is logged in and authorised to access the requested resource. |
| **Who Sets It** | MediFleet application server — set at login |
| **Applies To** | All clinical and administrative staff; not used for patient portal (see `patient_portal_token`) |
| **Expiry** | **15 minutes** from the time of issue. The session will expire automatically after 15 minutes of inactivity or token age. |
| **HttpOnly** | Yes — this cookie cannot be accessed by JavaScript running in the browser. This prevents cross-site scripting (XSS) attacks from stealing the token. |
| **Secure** | Yes — transmitted only over HTTPS encrypted connections. |
| **SameSite** | Strict — not transmitted with cross-site requests. |
| **Data Contained** | An encrypted, cryptographically signed token (JWT). Contains user role and session identifier. Does not contain passwords or plain-text personal data. |

---

### 2.2 `refresh_token`

| Attribute | Detail |
|---|---|
| **Name** | `refresh_token` |
| **Purpose** | Allows the MediFleet system to issue a new `access_token` when the current one expires, without requiring the user to log in again during a continuous working session. The refresh token is exchanged once for a new access token and is then rotated (a new refresh token is issued simultaneously). |
| **Who Sets It** | MediFleet application server — set at login |
| **Applies To** | All clinical and administrative staff |
| **Expiry** | **7 days** from the time of issue. After 7 days the user must log in again. |
| **HttpOnly** | Yes — inaccessible to JavaScript. |
| **Secure** | Yes — HTTPS only. |
| **SameSite** | Strict |
| **Rotation** | Each use of the refresh token results in immediate rotation. If a refresh token is used more than once (indicating it may have been stolen and replayed), the system will detect **"Refresh token reuse detected"**, invalidate the entire token family, and require the user to log in again. Staff who see this message must report it immediately to the IT Security team as it may indicate a security incident. |
| **Data Contained** | Encrypted, cryptographically signed token. Contains session family identifier. Does not contain passwords or personal data. |

---

### 2.3 `csrf_token`

| Attribute | Detail |
|---|---|
| **Name** | `csrf_token` |
| **Purpose** | Protects against Cross-Site Request Forgery (CSRF) attacks. Every form submission and state-changing request in MediFleet must include a valid CSRF token to verify that the request originated from the MediFleet application itself and not from a malicious external site. |
| **Who Sets It** | MediFleet application server |
| **Applies To** | All MediFleet users (staff and patients) |
| **Expiry** | Matches the current session; refreshed at each page load. |
| **HttpOnly** | No — the CSRF token must be readable by the MediFleet JavaScript client to include it in request headers. It is not a session authentication token. |
| **Secure** | Yes — HTTPS only. |
| **SameSite** | Strict |
| **Data Contained** | A cryptographically random value with no personal data. |

---

### 2.4 `patient_portal_token`

| Attribute | Detail |
|---|---|
| **Name** | `patient_portal_token` |
| **Purpose** | Authenticates a patient or their authorised representative on the MediFleet Patient Portal, allowing them to view their personal health records, appointment history, invoices, and consent records. |
| **Who Sets It** | MediFleet Patient Portal server — set at patient portal login |
| **Applies To** | Patients and authorised representatives using the Patient Portal only |
| **Expiry** | **60 minutes** from the time of issue. The portal session will expire after 60 minutes of inactivity or token age. Patients must log in again after expiry. |
| **HttpOnly** | Yes — inaccessible to JavaScript. |
| **Secure** | Yes — HTTPS only. |
| **SameSite** | Strict |
| **Data Contained** | Encrypted, cryptographically signed token. Contains patient portal session identifier. Does not contain passwords or plain-text personal data. |

---

## 3. SUMMARY TABLE

| Cookie Name | User Type | Expiry | HttpOnly | Purpose Category |
|---|---|---|---|---|
| `access_token` | Staff | 15 minutes | Yes | Authentication |
| `refresh_token` | Staff | 7 days | Yes | Session continuity / authentication |
| `csrf_token` | All users | Per session | No | Security (CSRF protection) |
| `patient_portal_token` | Patients | 60 minutes | Yes | Patient portal authentication |

---

## 4. COOKIES WE DO NOT USE

MediFleet does **not** set or use:

- Advertising or marketing cookies
- Third-party analytics cookies (e.g., Google Analytics)
- Social media tracking cookies or pixels
- Persistent preference cookies
- Any cookie that tracks behaviour across other websites

---

## 5. HOW TO MANAGE COOKIES

**For staff accessing MediFleet:**
MediFleet cookies are strictly necessary for the system to function. You cannot opt out of these cookies while using MediFleet. Blocking or deleting these cookies will prevent you from logging in or using the system. Do not use browser extensions that block all cookies while working in MediFleet.

**For patients using the Patient Portal:**
The Patient Portal cookies are strictly necessary for your secure access to your health records. If you clear your browser cookies, you will be logged out and will need to log in again.

**General browser settings:**
Most browsers allow you to view and delete cookies through their settings menu. Deleting MediFleet cookies will log you out of any active session. The cookies will be re-set at your next login.

---

## 6. SECURITY INCIDENT REPORTING

If you are a staff member and you see a message on the MediFleet system stating **"Refresh token reuse detected"** or any unexpected logout, you must:

1. Do not dismiss the message or attempt to log in again immediately.
2. Report the incident immediately to the IT Security team or the Data Protection Officer.
3. Complete an Incident Report Form (`OPERATIONS/INCIDENT_REPORT_FORM.md`).

This message may indicate that your session credentials have been compromised.

---

## 7. FURTHER INFORMATION

For questions about this policy, contact:

**Data Protection Officer:** [FILL IN — Name, Email, Phone]

**IT Security Team:** [FILL IN — Email, Phone]

**Office of the Data Protection Commissioner (ODPC):** www.odpc.go.ke

---

## DOCUMENT CONTROL

| Field | Detail |
|---|---|
| Version | 1.0 |
| Review Date | 2027-05-16 |
| Approved By | Data Protection Officer / IT Security Manager |
| Template File | `PRIVACY/COOKIE_POLICY.md` |
