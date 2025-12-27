# mcp_server/db_client.py
"""
Database client for Secure Hospital MCP - STANDALONE
-----------------------------------------------------
Psycopg2 helpers that return plain dicts, ready for JSON serialization.
No Django dependencies - pure SQL operations.
"""

import os
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from contextlib import contextmanager

load_dotenv()

@contextmanager
def get_db_cursor():
    """
    Context manager that yields a psycopg2 cursor
    and commits automatically.
    """
    conn = None
    try:
        dsn = os.getenv("DATABASE_URL_MCP") or os.getenv("DATABASE_URL")
        if not dsn:
            raise RuntimeError("DATABASE_URL_MCP or DATABASE_URL must be set")

        conn = psycopg2.connect(
            dsn,
            cursor_factory=psycopg2.extras.DictCursor,
        )
        cursor = conn.cursor()
        yield cursor
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


@contextmanager
def _conn():
    """
    Context manager that yields a psycopg2 connection with DictCursor.
    Used by _one, _many, and _execute helper functions.
    """
    conn = None
    try:
        dsn = os.getenv("DATABASE_URL_MCP") or os.getenv("DATABASE_URL")
        if not dsn:
            raise RuntimeError("DATABASE_URL_MCP or DATABASE_URL must be set")

        conn = psycopg2.connect(
            dsn,
            cursor_factory=psycopg2.extras.DictCursor,
        )
        yield conn
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


def _one(sql: str, params: tuple) -> Optional[Dict[str, Any]]:
    """Execute a query and return a single row as a dict."""
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None


def _many(sql: str, params: tuple) -> List[Dict[str, Any]]:
    """Execute a query and return all rows as a list of dicts."""
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
        return [dict(r) for r in rows]


def _execute(sql: str, params: tuple) -> None:
    """Execute a write query (INSERT/UPDATE/DELETE)."""
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        conn.commit()


# ============================================================
# PATIENT QUERIES
# ============================================================

def get_patient_overview(patient_id: str) -> Optional[Dict[str, Any]]:
    """Get basic patient demographics (Non-PHI)."""
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


# ============================================================
# ADMISSIONS
# ============================================================

def get_admissions_for_patient(patient_id: str) -> List[Dict[str, Any]]:
    """Get hospital admissions for a patient."""
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


# ============================================================
# APPOINTMENTS
# ============================================================

def get_appointments_for_patient(patient_id: str) -> List[Dict[str, Any]]:
    """Get appointments for a patient."""
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


# ============================================================
# MEDICAL RECORDS
# ============================================================

def get_medical_records_for_patient(patient_id: str) -> List[Dict[str, Any]]:
    """Get medical records for a patient."""
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


# ============================================================
# STAFF & SHIFTS
# ============================================================

def get_shifts_for_staff(staff_id: str) -> List[Dict[str, Any]]:
    """Get shifts for a specific staff member."""
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


def get_all_shifts(department: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Get all shifts, optionally filtered by department.
    Returns shift data with staff department info.
    """
    if department:
        sql = """
            SELECT
                sh.shift_id,
                sh.staff_id,
                sh.start_time,
                sh.end_time,
                s.department
            FROM ehr_shift AS sh
            LEFT JOIN ehr_staff AS s ON s.staff_id = sh.staff_id
            WHERE s.department ILIKE %s
            ORDER BY sh.start_time DESC
            LIMIT 50
        """
        return _many(sql, (f"%{department}%",))
    else:
        sql = """
            SELECT
                sh.shift_id,
                sh.staff_id,
                sh.start_time,
                sh.end_time,
                s.department
            FROM ehr_shift AS sh
            LEFT JOIN ehr_staff AS s ON s.staff_id = sh.staff_id
            ORDER BY sh.start_time DESC
            LIMIT 50
        """
        return _many(sql, ())


def get_staff_id_for_user(user_id: int) -> Optional[str]:
    """Get staff_id for a given user_id."""
    sql = """
        SELECT staff_id
        FROM ehr_staff
        WHERE user_id = %s
        LIMIT 1
    """
    result = _one(sql, (user_id,))
    return str(result["staff_id"]) if result else None
