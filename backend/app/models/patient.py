from sqlalchemy import Column, Integer, String, Boolean, Date, DateTime, ForeignKey, Index, Text
from sqlalchemy.sql import func
from app.config.database import Base
# M-1: KDPA column-level encryption for sensitive PHI / personal data. The
# EncryptedString type is a Text-backed Fernet TypeDecorator that decrypts on
# read (tolerating pre-migration plaintext) and encrypts on write. Apply ONLY
# to columns that are never used in SQL search/filter/index — encrypted
# ciphertext is non-deterministic so LIKE/index lookups can't work. Searchable
# identifiers (telephone_1, id_number, email) are deliberately left plaintext
# pending a blind-index follow-up.
from app.utils.db_types import EncryptedString

class Patient(Base):
    __tablename__ = "patients"

    patient_id = Column(Integer, primary_key=True)
    outpatient_no = Column(String(50), unique=True, index=True, nullable=False)
    inpatient_no = Column(String(50), unique=True, index=True, nullable=True)
    
    # 1. Basic Demographics
    surname = Column(String(100), nullable=False)
    other_names = Column(String(150), nullable=False)
    sex = Column(String(20), nullable=False)
    date_of_birth = Column(Date, nullable=False)
    marital_status = Column(String(50), nullable=True)
    religion = Column(String(100), nullable=True)
    primary_language = Column(String(100), nullable=True)
    
    # 2. Clinical Baselines
    blood_group = Column(String(10), nullable=True)
    # M-1: encrypted at rest (sensitive medical data, never searched).
    allergies = Column(EncryptedString, nullable=True)
    chronic_conditions = Column(EncryptedString, nullable=True)
    
    # 3. Identification & Contact
    id_type = Column(String(50), nullable=True)
    id_number = Column(String(100), index=True, nullable=True)
    nationality = Column(String(100), nullable=True)
    telephone_1 = Column(String(20), index=True, nullable=True)
    telephone_2 = Column(String(20), nullable=True)
    email = Column(String(255), nullable=True)
    
    # 4. Address & Employment
    # M-1: address / employment are personal data — encrypted at rest. (postal_code
    # and town are kept plaintext: coarse, low-sensitivity, useful for analytics.)
    postal_address = Column(EncryptedString, nullable=True)
    postal_code = Column(String(50), nullable=True)
    residence = Column(EncryptedString, nullable=True)
    town = Column(String(100), nullable=True)
    occupation = Column(EncryptedString, nullable=True)
    employer_name = Column(EncryptedString, nullable=True)
    reference_number = Column(String(100), nullable=True)

    # 5. Next of Kin
    # M-1: NOK name + contact are personal data — encrypted at rest.
    nok_name = Column(EncryptedString, nullable=True)
    nok_relationship = Column(String(100), nullable=True)
    nok_contact = Column(EncryptedString, nullable=True)

    # 6. Operational Meta
    # M-1: free-text notes can hold anything sensitive — encrypted at rest.
    notes = Column(EncryptedString, nullable=True)
    is_active = Column(Boolean, default=True)
    registered_on = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    registered_by = Column(Integer, ForeignKey("users.user_id"), index=True)

    # 7. Insurance Details (Mayo Clinic Standards)
    insurance_provider = Column(String(255), nullable=True)
    insurance_policy_number = Column(String(100), nullable=True)

    # 8. Patient-portal brute-force lockout (audit M-3). The self-service portal
    # verifies low-entropy knowledge factors (OP no. + DOB + last-4 phone). The
    # per-IP rate limit alone doesn't stop a rotating-IP attacker who knows a
    # target's OP no. from brute-forcing the 10^4 phone-suffix space, so we also
    # track failed attempts per patient and temporarily lock the record —
    # mirroring the staff-login lockout. Durable (DB, not Redis) so the control
    # never silently disappears when Redis is absent.
    portal_failed_attempts = Column(Integer, nullable=False, server_default="0", default=0)
    portal_locked_until = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index('idx_patient_name', 'surname', 'other_names'),
    )