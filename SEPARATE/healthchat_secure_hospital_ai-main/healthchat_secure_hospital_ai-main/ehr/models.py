"""
EHR Models – Secure Hospital Management System (with RBAC Notes)
----------------------------------------------------------------
Core data models for hospital operations with clear separation of
non-sensitive and sensitive (PHI) data.

Implements Role-Based Access Control (RBAC):
- Admins: full system access
- Doctors/Nurses: clinical data access
- Reception/Billing: limited to patient & appointment info
- Auditors: read-only access (including PHI)
"""

from django.db import models
from django.conf import settings
from .fields import ShortUUIDField


# ================================================================
# ENUM-LIKE CHOICES (used for validation and consistency)
# ================================================================
class AppointmentStatus(models.TextChoices):
    SCHEDULED = 'Scheduled', 'Scheduled'
    COMPLETED = 'Completed', 'Completed'
    CANCELED = 'Canceled', 'Canceled'
    NO_SHOW = 'No-Show', 'No-Show'


class PaymentStatus(models.TextChoices):
    PENDING = 'Pending', 'Pending'
    PAID = 'Paid', 'Paid'
    PARTIAL = 'Partial', 'Partial'
    REFUNDED = 'Refunded', 'Refunded'


# ================================================================
# STAFF MODEL
# ================================================================
class Staff(models.Model):
    """
    Represents hospital personnel (clinical + administrative).

    RBAC Access:
    - Admin: Full access
    - Doctor/Nurse: View & edit their own info
    - Reception/Billing: Read-only
    - Auditor: Read-only
    """

    STAFF_TYPES = [
        ("Doctor", "Doctor"),
        ("Nurse", "Nurse"),
        ("Admin", "Admin"),
        ("Billing", "Billing"),
        ("Reception", "Reception"),
        ("Other", "Other"),
    ]

    staff_id = ShortUUIDField(primary_key=True)
    full_name = models.CharField(max_length=255)
    staff_type = models.CharField(max_length=20, choices=STAFF_TYPES)
    specialization = models.CharField(max_length=255, null=True, blank=True)
    department = models.CharField(max_length=255, null=True, blank=True)
    phone = models.CharField(max_length=50, null=True, blank=True)
    email = models.EmailField(unique=True, null=True, blank=True)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return f"{self.full_name} ({self.staff_type})"


# ================================================================
# PATIENT MODEL (non-sensitive demographic info)
# ================================================================
class Patient(models.Model):
    """
    Stores general patient identifiers (non-PHI).

    RBAC Access:
    - Admin: Full access
    - Doctor/Nurse: View & edit patient basics
    - Reception: Create new patients, update contact basics
    - Billing: Read-only
    - Auditor: Read-only
    """

    patient_id = ShortUUIDField(primary_key=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    date_of_birth_year = models.IntegerField(null=True, blank=True)
    gender = models.CharField(max_length=10, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        permissions = [
            ("view_patient_basic", "Can view basic patient info (non-PHI)"),
            ("edit_patient_basic", "Can create/edit basic patient info"),
        ]
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


# ================================================================
# PHI DEMOGRAPHICS MODEL (highly sensitive)
# ================================================================
class PHIDemographics(models.Model):
    """
    Contains Protected Health Information (PHI).

    RBAC Access:
    - Admin: Full access
    - Doctor/Nurse: View limited fields (DOB, phone, insurance)
    - Billing: View insurance-only fields
    - Reception: No access
    - Auditor: Full read-only access (for compliance)
    """

    patient = models.OneToOneField(Patient, on_delete=models.CASCADE, primary_key=True)
    date_of_birth = models.DateField()
    address = models.TextField(null=True, blank=True)
    phone = models.CharField(max_length=50, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    social_security_number = models.CharField(max_length=20, unique=True, null=True, blank=True)
    emergency_contact = models.CharField(max_length=255, null=True, blank=True)
    insurance_provider = models.CharField(max_length=255, null=True, blank=True)
    insurance_number = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        permissions = [
            ("view_phi", "Can view full PHI (DOB, address, SSN, insurance)"),
            ("edit_phi", "Can create/edit PHI records"),
            ("view_insurance_phi", "Can view only insurance fields"),
        ]

    def __str__(self):
        return f"PHI for {self.patient}"


# ================================================================
# ADMISSIONS MODEL
# ================================================================
class Admission(models.Model):
    """
    Tracks patient admissions (inpatient stays).

    RBAC Access:
    - Admin: Full access
    - Doctor/Nurse: View & update assigned patients
    - Reception: Create admission entries
    - Billing: Read-only
    - Auditor: Read-only
    """

    admission_id = ShortUUIDField(primary_key=True)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    room_number = models.CharField(max_length=50, null=True, blank=True)
    admission_date = models.DateTimeField()
    discharge_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(discharge_date__gte=models.F('admission_date')) | models.Q(discharge_date__isnull=True),
                name='chk_discharge_date_valid'
            )
        ]
        ordering = ["-admission_date"]

    def __str__(self):
        return f"Admission {self.admission_id} for {self.patient}"


# ================================================================
# ADMISSION STAFF (relationship between staff and admissions)
# ================================================================
class AdmissionStaff(models.Model):
    """
    Maps which staff participated in a patient’s admission.

    RBAC Access:
    - Admin: Full access
    - Doctor/Nurse: View & update their assigned admissions
    - Reception/Billing: Read-only
    - Auditor: Read-only
    """

    admission_staff_id = ShortUUIDField(primary_key=True)
    admission = models.ForeignKey(Admission, on_delete=models.CASCADE)
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE)
    role_in_admission = models.CharField(max_length=50)

    class Meta:
        unique_together = ('admission', 'staff')

    def __str__(self):
        return f"{self.staff} → {self.admission}"


# ================================================================
# APPOINTMENTS MODEL
# ================================================================
class Appointment(models.Model):
    """
    Represents outpatient or follow-up appointments.

    RBAC Access:
    - Admin: Full access
    - Doctor/Nurse: View and manage assigned appointments
    - Reception: Create and reschedule appointments
    - Billing: Read-only
    - Auditor: Read-only
    """

    appointment_id = ShortUUIDField(primary_key=True)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    staff = models.ForeignKey(Staff, on_delete=models.SET_NULL, null=True)
    appointment_date = models.DateTimeField()
    status = models.CharField(max_length=20, choices=AppointmentStatus.choices, default=AppointmentStatus.SCHEDULED)
    notes = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ["-appointment_date"]

    def __str__(self):
        return f"Appointment {self.appointment_id} ({self.status})"


# ================================================================
# MEDICAL RECORDS MODEL
# ================================================================
class MedicalRecord(models.Model):
    """
    Contains clinical notes, diagnoses, and treatments.

    RBAC Access:
    - Admin: Full access
    - Doctor/Nurse: View & edit assigned patient records
    - Reception/Billing: No access
    - Auditor: Read-only (compliance reviews)
    """

    record_id = ShortUUIDField(primary_key=True)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    staff = models.ForeignKey(Staff, on_delete=models.SET_NULL, null=True)
    appointment = models.ForeignKey(Appointment, on_delete=models.SET_NULL, null=True, blank=True)
    diagnosis = models.TextField()
    treatment = models.TextField()
    visit_date = models.DateTimeField()

    class Meta:
        ordering = ["-visit_date"]

    def __str__(self):
        return f"Record {self.record_id} for {self.patient}"


# ================================================================
# SHIFT MODEL (staff scheduling)
# ================================================================
class Shift(models.Model):
    """
    Defines hospital staff working hours and schedules.

    RBAC Access:
    - Admin: Full access
    - Doctor/Nurse: View their own shifts
    - Reception: Read-only (for scheduling coordination)
    - Auditor: Read-only
    """

    shift_id = ShortUUIDField(primary_key=True)
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(end_time__gt=models.F('start_time')),
                name='chk_shift_time_valid'
            )
        ]
        ordering = ["-start_time"]

    def __str__(self):
        return f"Shift for {self.staff.full_name} ({self.start_time} - {self.end_time})"
