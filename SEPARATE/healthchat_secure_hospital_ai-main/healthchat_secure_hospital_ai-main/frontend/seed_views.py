"""
Hospital AI Integration Demo – Data Seeder (RBAC-aware)
------------------------------------------------------
Populates Azure PostgreSQL (via Django models) with realistic demo data.

Generates:
- Users & Staff (Doctor, Nurse, Admin, Billing, Reception, Auditor)
- Patients & PHI (with unique SSNs)
- Admissions, Appointments, Medical Records (specialty-biased), Shifts
- Audit Logs (for compliance / AI-access simulation)
- (Optional) Attaches users to Groups if RBAC bootstrap has run

Usage:
    python seed_demo_data.py

Notes:
- Idempotent-ish for dev: usernames/emails use Faker + role prefixes to reduce collisions.
- PHI SSNs are unique using Faker's `unique` context.
"""

import os
import django
import random
from datetime import timedelta
from django.utils import timezone
from faker import Faker

# ----------------------------------------------------------------------
# Django setup
# ----------------------------------------------------------------------
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "secure_hospital_ai.settings")
django.setup()

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import IntegrityError, transaction

from audit.models import UserRole, AuditLog
from ehr.models import (
    Staff,
    Patient,
    PHIDemographics,
    Admission,
    AdmissionStaff,
    Appointment,
    AppointmentStatus,
    MedicalRecord,
    Shift,
)

User = get_user_model()

fake = Faker()
Faker.seed(1337)
random.seed(1337)

# ----------------------------------------------------------------------
# Utility helpers
# ----------------------------------------------------------------------
def rand_gender():
    return random.choice(["Male", "Female", "Other"])

def rand_specialty():
    return random.choice([
        "Cardiology", "Emergency Medicine", "Neurology", "Oncology",
        "Orthopedics", "Pediatrics", "Internal Medicine",
        "Radiology", "Psychiatry"
    ])

def rand_department():
    return random.choice([
        "Emergency Dept", "ICU", "Cardiology", "Radiology",
        "Oncology", "Outpatient Clinic", "Pediatrics", "Administration"
    ])

def random_past_datetime(days_back=30):
    minutes_back = random.randint(0, days_back * 24 * 60)
    return timezone.now() - timedelta(minutes=minutes_back)

def random_future_or_now_datetime(days_forward=14):
    minutes_forward = random.randint(0, days_forward * 24 * 60)
    return timezone.now() + timedelta(minutes=minutes_forward)

def make_password():
    return "DemoPass123!"

ACTIONS = [
    "LOGIN", "VIEW_PATIENT_RECORD", "UPDATE_MEDICATION",
    "EXPORT_SUMMARY_TO_AI", "REQUEST_LLM_SUMMARY", "DISCHARGE_PATIENT"
]

# ----------------------------------------------------------------------
# Realistic diagnoses & treatments aligned to specialties
# ----------------------------------------------------------------------
COMMON_DIAGNOSES = [
    # ❤️ Cardiology
    "Hypertension",
    "Coronary Artery Disease",
    "Atrial Fibrillation",
    "Congestive Heart Failure",
    "Myocardial Infarction (STEMI/NSTEMI)",
    "Hyperlipidemia",
    "Angina Pectoris",
    "Post-Cardiac Stent Follow-up",

    # 🏥 Emergency Medicine
    "Acute Appendicitis",
    "Sepsis",
    "Dehydration",
    "Anaphylaxis",
    "Acute Kidney Injury",
    "Laceration – Simple Repair",
    "Closed Distal Radius Fracture",

    # 🧠 Neurology
    "Migraine Headache",
    "Epilepsy",
    "Transient Ischemic Attack (TIA)",
    "Ischemic Stroke",
    "Parkinson’s Disease",
    "Multiple Sclerosis",
    "Peripheral Neuropathy",

    # 🎗 Oncology
    "Breast Cancer – Chemo Follow-up",
    "Non–Small Cell Lung Cancer",
    "Prostate Cancer",
    "Acute Lymphoblastic Leukemia (Remission)",
    "Colorectal Cancer",
    "Hodgkin Lymphoma",
    "Cutaneous Melanoma",

    # 🦴 Orthopedics
    "Osteoarthritis – Knee",
    "Rheumatoid Arthritis",
    "Total Knee Arthroplasty – Post-op",
    "Hip Fracture",
    "Carpal Tunnel Syndrome",
    "Lumbar Disc Herniation",
    "Adolescent Idiopathic Scoliosis",

    # 👶 Pediatrics
    "Acute Otitis Media",
    "Group A Strep Pharyngitis",
    "Pediatric Asthma Exacerbation",
    "Viral Gastroenteritis",
    "Febrile Seizure",
    "ADHD – Initial Evaluation",
    "Pediatric Obesity",

    # 💊 Internal Medicine
    "Type 2 Diabetes Mellitus",
    "Hypothyroidism",
    "Vitamin D Deficiency",
    "Gastroesophageal Reflux Disease (GERD)",
    "Iron Deficiency Anemia",
    "Obesity (BMI > 30)",
    "Chronic Kidney Disease – Stage 3",

    # 🩻 Radiology (study-driven visit reasons)
    "CT Abdomen – RLQ Pain Evaluation",
    "Chest X-ray – Pneumonia",
    "MRI Lumbar Spine – Degeneration",
    "RUQ Ultrasound – Cholelithiasis",
    "Screening Mammogram – Abnormal",
    "CT Head – Trauma Screening",

    # 🧠 Psychiatry
    "Major Depressive Disorder",
    "Generalized Anxiety Disorder",
    "Bipolar Disorder Type II",
    "Post-Traumatic Stress Disorder (PTSD)",
    "Schizophrenia – Medication Management",
    "Primary Insomnia",
    "Alcohol Use Disorder",
]

COMMON_TREATMENTS = [
    # ❤️ Cardiology
    "Start lisinopril 10 mg daily",
    "Prescribe atorvastatin 40 mg nightly",
    "Start metoprolol tartrate 25 mg BID",
    "Order EKG and echocardiogram",
    "Schedule exercise stress test",
    "Continue aspirin 81 mg daily",
    "Cardiology clinic follow-up in 4 weeks",

    # 🏥 Emergency Medicine
    "Administer 1L normal saline bolus",
    "Order CBC, CMP, lactate, blood cultures",
    "Start IV ceftriaxone 1 g",
    "Irrigate and suture laceration under sterile technique",
    "Apply volar wrist splint",
    "Continuous vitals and urine output monitoring",
    "Admit to ICU for sepsis protocol",

    # 🧠 Neurology
    "Start topiramate for migraine prophylaxis",
    "Administer tPA – within window criteria",
    "Refer for EEG and neurology consult",
    "Start levetiracetam 500 mg BID",
    "Neuro checks q4h",
    "Initiate physical therapy for gait instability",

    # 🎗 Oncology
    "Continue chemotherapy (cycle 4)",
    "Administer ondansetron pre-chemotherapy",
    "Order PET-CT for restaging",
    "Oncology nutrition counseling",
    "Trend tumor markers (CEA/CA-125/PSA as appropriate)",
    "Plan radiation therapy mapping",

    # 🦴 Orthopedics
    "Apply short leg cast and provide cast care instructions",
    "Refer to physical therapy 3x/week",
    "Order MRI to evaluate meniscal tear",
    "Ibuprofen 600 mg q6h PRN pain",
    "Partial weight-bearing with crutches",
    "Reinforce post-op wound care and DVT precautions",

    # 👶 Pediatrics
    "Amoxicillin 500 mg TID x10 days",
    "Albuterol nebulizer PRN wheeze",
    "Hydration, antipyretics, and rest",
    "Administer DTaP booster",
    "Refer to developmental pediatrics",
    "Pediatric clinic follow-up in 2 weeks",

    # 💊 Internal Medicine
    "Start metformin 500 mg BID with meals",
    "Recheck HbA1c in 3 months",
    "Start levothyroxine 50 mcg daily on empty stomach",
    "Low-sodium, heart-healthy diet education",
    "Encourage 30 minutes daily aerobic exercise",
    "Continue maintenance inhaler (fluticasone/salmeterol)",
    "Monitor eGFR and adjust meds accordingly",

    # 🩻 Radiology (orders & coordination)
    "Schedule MRI with gadolinium contrast",
    "Plan ultrasound-guided core needle biopsy",
    "Review CT results with radiologist",
    "Communicate critical results to referring clinician",
    "Obtain and document IV contrast informed consent",
    "Provide imaging disc and report to specialist",

    # 🧠 Psychiatry
    "Start sertraline 50 mg daily",
    "Refer for cognitive behavioral therapy (CBT)",
    "Baseline labs prior to lithium initiation",
    "Suicide risk assessment and safety planning",
    "Daily mindfulness/journaling exercises",
    "Adjust risperidone dose per psychiatrist",
    "Enroll in outpatient substance use program",
]

# ----------------------------------------------------------------------
# Specialty-aligned catalogs (subsets pulled from COMMON_* lists above)
# ----------------------------------------------------------------------
SPECIALTY_DIAGNOSES = {
    "Cardiology": [
        "Hypertension", "Coronary Artery Disease", "Atrial Fibrillation",
        "Congestive Heart Failure", "Myocardial Infarction (STEMI/NSTEMI)",
        "Hyperlipidemia", "Angina Pectoris", "Post-Cardiac Stent Follow-up",
    ],
    "Emergency Medicine": [
        "Acute Appendicitis", "Sepsis", "Dehydration", "Anaphylaxis",
        "Acute Kidney Injury", "Laceration – Simple Repair",
        "Closed Distal Radius Fracture",
    ],
    "Neurology": [
        "Migraine Headache", "Epilepsy", "Transient Ischemic Attack (TIA)",
        "Ischemic Stroke", "Parkinson’s Disease", "Multiple Sclerosis",
        "Peripheral Neuropathy",
    ],
    "Oncology": [
        "Breast Cancer – Chemo Follow-up", "Non–Small Cell Lung Cancer",
        "Prostate Cancer", "Acute Lymphoblastic Leukemia (Remission)",
        "Colorectal Cancer", "Hodgkin Lymphoma", "Cutaneous Melanoma",
    ],
    "Orthopedics": [
        "Osteoarthritis – Knee", "Rheumatoid Arthritis",
        "Total Knee Arthroplasty – Post-op", "Hip Fracture",
        "Carpal Tunnel Syndrome", "Lumbar Disc Herniation",
        "Adolescent Idiopathic Scoliosis",
    ],
    "Pediatrics": [
        "Acute Otitis Media", "Group A Strep Pharyngitis",
        "Pediatric Asthma Exacerbation", "Viral Gastroenteritis",
        "Febrile Seizure", "ADHD – Initial Evaluation", "Pediatric Obesity",
    ],
    "Internal Medicine": [
        "Type 2 Diabetes Mellitus", "Hypothyroidism", "Vitamin D Deficiency",
        "Gastroesophageal Reflux Disease (GERD)", "Iron Deficiency Anemia",
        "Obesity (BMI > 30)", "Chronic Kidney Disease – Stage 3",
    ],
    "Radiology": [
        "CT Abdomen – RLQ Pain Evaluation", "Chest X-ray – Pneumonia",
        "MRI Lumbar Spine – Degeneration", "RUQ Ultrasound – Cholelithiasis",
        "Screening Mammogram – Abnormal", "CT Head – Trauma Screening",
    ],
    "Psychiatry": [
        "Major Depressive Disorder", "Generalized Anxiety Disorder",
        "Bipolar Disorder Type II", "Post-Traumatic Stress Disorder (PTSD)",
        "Schizophrenia – Medication Management", "Primary Insomnia",
        "Alcohol Use Disorder",
    ],
}

SPECIALTY_TREATMENTS = {
    "Cardiology": [
        "Start lisinopril 10 mg daily", "Prescribe atorvastatin 40 mg nightly",
        "Start metoprolol tartrate 25 mg BID", "Order EKG and echocardiogram",
        "Schedule exercise stress test", "Continue aspirin 81 mg daily",
        "Cardiology clinic follow-up in 4 weeks",
    ],
    "Emergency Medicine": [
        "Administer 1L normal saline bolus", "Order CBC, CMP, lactate, blood cultures",
        "Start IV ceftriaxone 1 g", "Irrigate and suture laceration under sterile technique",
        "Apply volar wrist splint", "Continuous vitals and urine output monitoring",
        "Admit to ICU for sepsis protocol",
    ],
    "Neurology": [
        "Start topiramate for migraine prophylaxis", "Administer tPA – within window criteria",
        "Refer for EEG and neurology consult", "Start levetiracetam 500 mg BID",
        "Neuro checks q4h", "Initiate physical therapy for gait instability",
    ],
    "Oncology": [
        "Continue chemotherapy (cycle 4)", "Administer ondansetron pre-chemotherapy",
        "Order PET-CT for restaging", "Oncology nutrition counseling",
        "Trend tumor markers (CEA/CA-125/PSA as appropriate)", "Plan radiation therapy mapping",
    ],
    "Orthopedics": [
        "Apply short leg cast and provide cast care instructions", "Refer to physical therapy 3x/week",
        "Order MRI to evaluate meniscal tear", "Ibuprofen 600 mg q6h PRN pain",
        "Partial weight-bearing with crutches", "Reinforce post-op wound care and DVT precautions",
    ],
    "Pediatrics": [
        "Amoxicillin 500 mg TID x10 days", "Albuterol nebulizer PRN wheeze",
        "Hydration, antipyretics, and rest", "Administer DTaP booster",
        "Refer to developmental pediatrics", "Pediatric clinic follow-up in 2 weeks",
    ],
    "Internal Medicine": [
        "Start metformin 500 mg BID with meals", "Recheck HbA1c in 3 months",
        "Start levothyroxine 50 mcg daily on empty stomach", "Low-sodium, heart-healthy diet education",
        "Encourage 30 minutes daily aerobic exercise", "Continue maintenance inhaler (fluticasone/salmeterol)",
        "Monitor eGFR and adjust meds accordingly",
    ],
    "Radiology": [
        "Schedule MRI with gadolinium contrast", "Plan ultrasound-guided core needle biopsy",
        "Review CT results with radiologist", "Communicate critical results to referring clinician",
        "Obtain and document IV contrast informed consent", "Provide imaging disc and report to specialist",
    ],
    "Psychiatry": [
        "Start sertraline 50 mg daily", "Refer for cognitive behavioral therapy (CBT)",
        "Baseline labs prior to lithium initiation", "Suicide risk assessment and safety planning",
        "Daily mindfulness/journaling exercises", "Adjust risperidone dose per psychiatrist",
        "Enroll in outpatient substance use program",
    ],
}

def pick_for_specialty(staff_obj):
    """
    Return (diagnosis, treatment) lists suitable for the staff member's specialty.
    Falls back to Internal Medicine if specialty not mapped or staff is non-clinical.
    """
    specialty = (staff_obj.specialization or staff_obj.department or "").strip()
    key = None
    if specialty in SPECIALTY_DIAGNOSES:
        key = specialty
    else:
        for k in SPECIALTY_DIAGNOSES.keys():
            if k.lower() in specialty.lower():
                key = k
                break
    if key:
        return SPECIALTY_DIAGNOSES[key], SPECIALTY_TREATMENTS[key]
    return SPECIALTY_DIAGNOSES["Internal Medicine"], SPECIALTY_TREATMENTS["Internal Medicine"]

# ----------------------------------------------------------------------
# RBAC helpers (optional)
# ----------------------------------------------------------------------
def attach_user_to_group_if_exists(user, role_name: str):
    """
    If Django Group with the role name exists (after running bootstrap_rbac),
    attach the user to that group. Otherwise do nothing.
    """
    try:
        group = Group.objects.get(name=role_name)
        user.groups.clear()
        user.groups.add(group)
    except Group.DoesNotExist:
        # Fine in first-time setups; bootstrap_rbac can be run later.
        pass

# ----------------------------------------------------------------------
# Creators
# ----------------------------------------------------------------------
def create_staff(
    num_doctors=15,
    num_nurses=25,
    num_admins=4,
    num_billing=6,
    num_reception=6,
    num_auditors=2,
):
    """
    Create user accounts across roles and a linked Staff record (except Auditors).
    - Admin/Billing/Reception get Staff entries for realism (Admin in Administration).
    - Auditors are users without Staff (read-only compliance role).
    """
    staff_pool = []

    def _mk_user_and_staff(first, last, role, staff_type=None):
        """
        Create a User + optional Staff entry depending on role.
        """
        base = f"{first}.{last}".lower()
        for attempt in range(5):
            username = f"{role[:3].lower()}_{base}{'' if attempt == 0 else str(attempt)}"
            email = f"{username}@hospital.demo"
            try:
                with transaction.atomic():
                    user = User.objects.create_user(
                        username=username,
                        email=email,
                        role=role,
                        password=make_password(),
                    )
                break
            except IntegrityError:
                continue
        else:
            user = User.objects.create_user(
                username=f"{role[:3].lower()}_{base}_{fake.random_int(1000,9999)}",
                email=f"{role[:3].lower()}_{base}_{fake.random_int(1000,9999)}@hospital.demo",
                role=role,
                password=make_password(),
            )

        attach_user_to_group_if_exists(user, role)

        if role in (UserRole.DOCTOR, UserRole.NURSE, UserRole.ADMIN, UserRole.BILLING, UserRole.RECEPTION):
            staff = Staff.objects.create(
                user=user,
                full_name=(f"Dr. {first} {last}" if role == UserRole.DOCTOR else f"{first} {last}"),
                staff_type=staff_type or (
                    "Doctor" if role == UserRole.DOCTOR else
                    "Nurse" if role == UserRole.NURSE else
                    "Admin" if role == UserRole.ADMIN else
                    "Billing" if role == UserRole.BILLING else
                    "Reception"
                ),
                specialization=(rand_specialty() if role == UserRole.DOCTOR else None),
                department=("Administration" if role in (UserRole.ADMIN, UserRole.BILLING, UserRole.RECEPTION) else rand_department()),
                phone=fake.phone_number(),
                email=user.email,
            )
            staff_pool.append(staff)

        return user

    # Doctors
    for _ in range(num_doctors):
        first, last = fake.first_name(), fake.last_name()
        _mk_user_and_staff(first, last, UserRole.DOCTOR, staff_type="Doctor")

    # Nurses
    for _ in range(num_nurses):
        first, last = fake.first_name(), fake.last_name()
        _mk_user_and_staff(first, last, UserRole.NURSE, staff_type="Nurse")

    # Admins
    for _ in range(num_admins):
        first, last = fake.first_name(), fake.last_name()
        _mk_user_and_staff(first, last, UserRole.ADMIN, staff_type="Admin")

    # Billing
    for _ in range(num_billing):
        first, last = fake.first_name(), fake.last_name()
        _mk_user_and_staff(first, last, UserRole.BILLING, staff_type="Billing")

    # Reception
    for _ in range(num_reception):
        first, last = fake.first_name(), fake.last_name()
        _mk_user_and_staff(first, last, UserRole.RECEPTION, staff_type="Reception")

    # Auditors (no Staff record)
    for _ in range(num_auditors):
        first, last = fake.first_name(), fake.last_name()
        base = f"{first}.{last}".lower()
        for attempt in range(5):
            username = f"aud_{base}{'' if attempt == 0 else str(attempt)}"
            email = f"{username}@hospital.demo"
            try:
                with transaction.atomic():
                    user = User.objects.create_user(
                        username=username,
                        email=email,
                        role=UserRole.AUDITOR,
                        password=make_password(),
                    )
                break
            except IntegrityError:
                continue
        else:
            user = User.objects.create_user(
                username=f"aud_{base}_{fake.random_int(1000,9999)}",
                email=f"aud_{base}_{fake.random_int(1000,9999)}@hospital.demo",
                role=UserRole.AUDITOR,
                password=make_password(),
            )
        attach_user_to_group_if_exists(user, UserRole.AUDITOR)

    return staff_pool


def create_patients(num_patients=200):
    """
    Create Patients + PHI with unique SSNs.
    """
    patients = []
    fake_unique = Faker()
    fake_unique.seed_instance(2025)
    fake_unique.unique.clear()

    for _ in range(num_patients):
        first, last = fake.first_name(), fake.last_name()
        dob_date = fake.date_of_birth(minimum_age=1, maximum_age=95)

        p = Patient.objects.create(
            first_name=first,
            last_name=last,
            date_of_birth_year=dob_date.year,
            gender=rand_gender(),
        )

        for _retry in range(5):
            try:
                PHIDemographics.objects.create(
                    patient=p,
                    date_of_birth=dob_date,
                    address=fake.address(),
                    phone=fake.phone_number(),
                    email=f"{first.lower()}.{last.lower()}@patient.demo",
                    social_security_number=fake_unique.unique.ssn(),
                    emergency_contact=fake.name(),
                    insurance_provider=random.choice(["Aetna", "Blue Cross", "Cigna", "Medicare"]),
                    insurance_number=f"INS-{fake.bothify('####-####-####')}",
                )
                break
            except IntegrityError:
                fake_unique.unique.clear()
        patients.append(p)
    return patients


def create_admissions(patients, staff_pool, count=100):
    """
    Admissions + assigned staff (1–3). Doctors become 'Attending Physician',
    Nurses become 'Primary Nurse'.
    """
    admissions = []
    doctor_staff = [s for s in staff_pool if s.staff_type == "Doctor"]
    nurse_staff = [s for s in staff_pool if s.staff_type == "Nurse"]
    any_staff = staff_pool

    for _ in range(count):
        p = random.choice(patients)
        start = random_past_datetime(20)
        end = start + timedelta(hours=random.randint(4, 72)) if random.random() < 0.6 else None

        a = Admission.objects.create(
            patient=p,
            room_number=str(random.randint(100, 550)),
            admission_date=start,
            discharge_date=end,
        )

        assigned = set()
        if doctor_staff:
            d = random.choice(doctor_staff)
            assigned.add(d.pk)
            AdmissionStaff.objects.create(admission=a, staff=d, role_in_admission="Attending Physician")
        if nurse_staff and (random.random() < 0.9):
            n = random.choice(nurse_staff)
            if n.pk not in assigned:
                assigned.add(n.pk)
                AdmissionStaff.objects.create(admission=a, staff=n, role_in_admission="Primary Nurse")

        if random.random() < 0.4 and any_staff:
            st = random.choice(any_staff)
            if st.pk not in assigned:
                AdmissionStaff.objects.create(
                    admission=a,
                    staff=st,
                    role_in_admission=("Consulting Physician" if st.staff_type == "Doctor" else "Support Staff")
                )
        admissions.append(a)
    return admissions


def create_appointments(patients, staff_pool, count=400):
    """
    Mix of past and future appointments; prefer Doctor/Nurse as providers.
    """
    appts = []
    providers = [s for s in staff_pool if s.staff_type in ("Doctor", "Nurse")]
    providers = providers or staff_pool

    for _ in range(count):
        p, s = random.choice(patients), random.choice(providers)

        if random.random() < 0.6:
            date = random_past_datetime(10)
            status = random.choice([
                AppointmentStatus.COMPLETED,
                AppointmentStatus.CANCELED,
                AppointmentStatus.NO_SHOW,
            ])
        else:
            date = random_future_or_now_datetime(10)
            status = AppointmentStatus.SCHEDULED

        appt = Appointment.objects.create(
            patient=p,
            staff=s,
            appointment_date=date,
            status=status,
            notes=fake.sentence(nb_words=10),
        )
        appts.append(appt)
    return appts


def pick_for_specialty(staff_obj):
    """
    Return (diagnosis, treatment) lists suitable for the staff member's specialty.
    Falls back to Internal Medicine if specialty not mapped or staff is non-clinical.
    """
    specialty = (staff_obj.specialization or staff_obj.department or "").strip()
    key = None
    if specialty in SPECIALTY_DIAGNOSES:
        key = specialty
    else:
        for k in SPECIALTY_DIAGNOSES.keys():
            if k.lower() in specialty.lower():
                key = k
                break
    if key:
        return SPECIALTY_DIAGNOSES[key], SPECIALTY_TREATMENTS[key]
    return SPECIALTY_DIAGNOSES["Internal Medicine"], SPECIALTY_TREATMENTS["Internal Medicine"]


def create_records(patients, staff_pool, appts, count=300):
    """
    Generate MedicalRecord items linked to patients and appointments,
    with diagnoses/treatments biased by the provider's specialty.
    """
    providers = [s for s in staff_pool if s.staff_type in ("Doctor", "Nurse")]
    providers = providers or staff_pool

    for _ in range(count):
        provider = random.choice(providers)
        dx_list, tx_list = pick_for_specialty(provider)

        MedicalRecord.objects.create(
            patient=random.choice(patients),
            staff=provider,
            appointment=random.choice(appts),
            diagnosis=random.choice(dx_list),
            treatment=random.choice(tx_list),
            visit_date=random_past_datetime(21),
        )


def create_shifts(staff_pool, count=150):
    """
    Create shift data for a random subset of staff.
    """
    for _ in range(count):
        st = random.choice(staff_pool)
        start = random_past_datetime(15)
        end = start + timedelta(hours=random.randint(6, 12))
        Shift.objects.create(staff=st, start_time=start, end_time=end)


def create_audits(staff_pool, count=500):
    """
    Simulate audit events; mark PHI access events for visibility.
    """
    for _ in range(count):
        s = random.choice(staff_pool)
        action = random.choice(ACTIONS)
        AuditLog.objects.create(
            user=s.user,
            action=action,
            table_name=random.choice(["Patient", "PHIDemographics", "Appointment", "MedicalRecord", "Admission"]),
            ip_address=fake.ipv4_public(),
            is_phi_access=(action in ["VIEW_PATIENT_RECORD", "EXPORT_SUMMARY_TO_AI"]),
        )


# ----------------------------------------------------------------------
# Entrypoint
# ----------------------------------------------------------------------
if __name__ == "__main__":
    print("🚀 Seeding hospital demo data...")

    staff_pool = create_staff(
        num_doctors=15,
        num_nurses=25,
        num_admins=4,
        num_billing=6,
        num_reception=6,
        num_auditors=2,
    )
    patients = create_patients(200)
    admissions = create_admissions(patients, staff_pool, count=100)
    appointments = create_appointments(patients, staff_pool, count=400)
    create_records(patients, staff_pool, appointments, count=300)
    create_shifts(staff_pool, count=150)
    create_audits(staff_pool, count=500)

    print("✅ Seeding complete — demo hospital data successfully inserted.")
    print(f"👩‍⚕️ Staff:        {Staff.objects.count()}")
    print(f"🧑‍🦰 Patients:     {Patient.objects.count()}")
    print(f"🛡️  PHI rows:      {PHIDemographics.objects.count()}")
    print(f"🏥 Admissions:     {Admission.objects.count()}")
    print(f"👥 AdmissionStaff: {AdmissionStaff.objects.count()}")
    print(f"📅 Appointments:   {Appointment.objects.count()}")
    print(f"🩺 Records:        {MedicalRecord.objects.count()}")
    print(f"🕑 Shifts:         {Shift.objects.count()}")
    print(f"🔐 Audit logs:     {AuditLog.objects.count()}")
