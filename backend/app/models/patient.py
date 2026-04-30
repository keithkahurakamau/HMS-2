from sqlalchemy import Column, Integer, String, Boolean, Date, DateTime, ForeignKey, Index, Text
from sqlalchemy.sql import func
from app.config.database import Base

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
    allergies = Column(Text, nullable=True)
    chronic_conditions = Column(Text, nullable=True)
    
    # 3. Identification & Contact
    id_type = Column(String(50), nullable=True)
    id_number = Column(String(100), index=True, nullable=True)
    nationality = Column(String(100), nullable=True)
    telephone_1 = Column(String(20), index=True, nullable=True)
    telephone_2 = Column(String(20), nullable=True)
    email = Column(String(255), nullable=True)
    
    # 4. Address & Employment
    postal_address = Column(String(255), nullable=True)
    postal_code = Column(String(50), nullable=True)
    residence = Column(String(255), nullable=True)
    town = Column(String(100), nullable=True)
    occupation = Column(String(100), nullable=True)
    employer_name = Column(String(255), nullable=True)
    reference_number = Column(String(100), nullable=True)
    
    # 5. Next of Kin
    nok_name = Column(String(255), nullable=True)
    nok_relationship = Column(String(100), nullable=True)
    nok_contact = Column(String(100), nullable=True)
    
    # 6. Operational Meta
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    registered_on = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    registered_by = Column(Integer, ForeignKey("users.user_id"), index=True)

    # 7. Insurance Details (Mayo Clinic Standards)
    insurance_provider = Column(String(255), nullable=True)
    insurance_policy_number = Column(String(100), nullable=True)

    __table_args__ = (
        Index('idx_patient_name', 'surname', 'other_names'),
    )