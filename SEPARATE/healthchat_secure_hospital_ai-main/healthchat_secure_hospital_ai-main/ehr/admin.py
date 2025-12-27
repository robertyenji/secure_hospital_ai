from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import (
    Staff, Patient, PHIDemographics, Admission, AdmissionStaff,
    Appointment, MedicalRecord, Shift
)

@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    list_display = ("full_name", "staff_type", "department", "specialization", "email")
    list_filter = ("staff_type", "department")
    search_fields = ("full_name", "email", "specialization")
    ordering = ("full_name",)


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "patient_id", "gender", "date_of_birth_year", "created_at")
    search_fields = ("first_name", "last_name")
    list_filter = ("gender",)
    ordering = ("last_name",)


@admin.register(PHIDemographics)
class PHIDemographicsAdmin(admin.ModelAdmin):
    """
    Sensitive PHI section — restricts viewing and editing to authorized roles.
    """
    list_display = ("patient", "date_of_birth", "insurance_provider")
    search_fields = ("patient__first_name", "patient__last_name", "insurance_provider")
    readonly_fields = ("social_security_number",)

    def has_view_permission(self, request, obj=None):
        # Only Admins and Auditors can view PHI directly
        return request.user.role in ["Admin", "Auditor"]

    def has_change_permission(self, request, obj=None):
        return request.user.role in ["Admin"]

    def has_delete_permission(self, request, obj=None):
        return request.user.role == "Admin"


@admin.register(Admission)
class AdmissionAdmin(admin.ModelAdmin):
    list_display = ("admission_id", "patient", "room_number", "admission_date", "discharge_date")
    list_filter = ("admission_date", "discharge_date")
    search_fields = ("patient__first_name", "patient__last_name", "room_number")
    ordering = ("-admission_date",)


@admin.register(AdmissionStaff)
class AdmissionStaffAdmin(admin.ModelAdmin):
    list_display = ("admission", "staff", "role_in_admission")
    search_fields = ("admission__admission_id", "staff__full_name", "role_in_admission")


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ("appointment_id", "patient", "staff", "appointment_date", "status")
    list_filter = ("status", "appointment_date")
    search_fields = ("patient__first_name", "patient__last_name", "staff__full_name")
    ordering = ("-appointment_date",)


@admin.register(MedicalRecord)
class MedicalRecordAdmin(admin.ModelAdmin):
    list_display = ("record_id", "patient", "staff", "visit_date", "diagnosis")
    search_fields = ("patient__first_name", "patient__last_name", "diagnosis", "treatment")
    list_filter = ("visit_date",)
    ordering = ("-visit_date",)


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ("staff", "start_time", "end_time")
    search_fields = ("staff__full_name", "staff__id")
    list_filter = ("staff__department",)
    ordering = ("-start_time",)
