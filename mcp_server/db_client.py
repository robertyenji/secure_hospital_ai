# mcp_server/db_client.py
"""
Database client for Secure Hospital MCP
---------------------------------------
Psycopg2 helpers that return plain dicts, ready for JSON serialization.
"""

import os
import psycopg2
import psycopg2.extras
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
load_dotenv()

def _conn():
    """Open a DB connection for MCP."""
    dsn = os.getenv("DATABASE_URL_MCP")
    if dsn:
        return psycopg2.connect(
            dsn,
            cursor_factory=psycopg2.extras.DictCursor,
        )

    return psycopg2.connect(
        host=os.getenv("PGHOST"),
        database=os.getenv("PGDATABASE"),
        user=os.getenv("PGUSER"),
        password=os.getenv("PGPASSWORD"),
        port=os.getenv("PGPORT", 5432),
        sslmode=os.getenv("MCP_DB_SSLMODE", "require"),
        cursor_factory=psycopg2.extras.DictCursor,
    )

def _one(sql: str, params: tuple) -> Optional[Dict[str, Any]]:
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None

def _many(sql: str, params: tuple) -> List[Dict[str, Any]]:
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
        return [dict(r) for r in rows]

# === Patient Overview (Non-PHI) ===

def get_patient_overview(patient_id: str) -> Optional[Dict[str, Any]]:
    sql = """
        SELECT
            p.patient_id,
            p.first_name,
            p.last_name,
            p.date_of_birth_year,
            p.gender,
            p.created_at
        FROM ehr_patient AS p
        WHERE p.patient_id = %s
        LIMIT 1
    """
    return _one(sql, (patient_id,))

# === Patient PHI (Protected Health Information) ===

def get_patient_phi(patient_id: str) -> Optional[Dict[str, Any]]:
    """
    Get Protected Health Information including SSN, full DOB, address, insurance.
    REQUIRES: Admin, Doctor, Nurse, or Auditor role (enforced by MCP main.py)
    """
    sql = """
        SELECT
            d.patient_id,
            d.date_of_birth,
            d.address,
            d.phone,
            d.email,
            d.social_security_number,
            d.emergency_contact,
            d.insurance_provider,
            d.insurance_number
        FROM ehr_phidemographics AS d
        WHERE d.patient_id = %s
        LIMIT 1
    """
    return _one(sql, (patient_id,))

# === Admissions ===

def get_admissions_for_patient(patient_id: str) -> List[Dict[str, Any]]:
    sql = """
        SELECT
            a.admission_id,
            a.patient_id,
            a.room_number,
            a.admission_date,
            a.discharge_date
        FROM ehr_admission AS a
        WHERE a.patient_id = %s
        ORDER BY a.admission_date DESC
    """
    return _many(sql, (patient_id,))

# === Appointments ===

def get_appointments_for_patient(patient_id: str) -> List[Dict[str, Any]]:
    sql = """
        SELECT
            ap.appointment_id,
            ap.patient_id,
            ap.staff_id,
            s.full_name AS staff_name,
            ap.appointment_date,
            ap.status,
            ap.notes
        FROM ehr_appointment AS ap
        LEFT JOIN ehr_staff AS s
          ON s.staff_id = ap.staff_id
        WHERE ap.patient_id = %s
        ORDER BY ap.appointment_date DESC
    """
    return _many(sql, (patient_id,))

# === Medical Records ===

def get_medical_records_for_patient(patient_id: str) -> List[Dict[str, Any]]:
    sql = """
        SELECT
            mr.record_id,
            mr.patient_id,
            mr.appointment_id,
            mr.staff_id,
            s.full_name AS staff_name,
            mr.diagnosis,
            mr.treatment,
            mr.visit_date
        FROM ehr_medicalrecord AS mr
        LEFT JOIN ehr_staff AS s
          ON s.staff_id = mr.staff_id
        WHERE mr.patient_id = %s
        ORDER BY mr.visit_date DESC
    """
    return _many(sql, (patient_id,))

# === Staff Shifts ===

def get_shifts_for_staff(staff_id: str) -> List[Dict[str, Any]]:
    sql = """
        SELECT
            sh.shift_id,
            sh.staff_id,
            sh.start_time,
            sh.end_time
        FROM ehr_shift AS sh
        WHERE sh.staff_id = %s
        ORDER BY sh.start_time DESC
    """
    return _many(sql, (staff_id,))