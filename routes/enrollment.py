"""
routes/enrollment.py - Enrollment & Cohort Routing Blueprint
Fulfills Phase 23 (Monolith Modularization) of INTERNSHIPPORTAL4_LOCAL_AI_AGENT_MASTER_PLAN.md

Endpoints:
- POST /cohort/<int:cohort_id>/enroll
- POST /attendance/ping
"""
from flask import Blueprint, jsonify, request
from services.auth_service import AuthService
from app import (
    get_db, now_str, log_error, clean_text,
    current_intern
)

enrollment_bp = Blueprint("enrollment", __name__)


@enrollment_bp.route("/cohort/<int:cohort_id>/enroll", methods=["POST"])
def cohort_enroll(cohort_id):
    """Enrolls the logged-in intern into a cohort with atomic capacity enforcement."""
    with get_db() as conn:
        intern = AuthService.current_intern(conn)
    if not intern:
        return jsonify({"status": "error", "message": "Authentication required"}), 401

    try:
        with get_db() as conn:
            cohort = conn.execute("SELECT * FROM cohorts WHERE id=?", (cohort_id,)).fetchone()
            if not cohort:
                return jsonify({"status": "error", "message": "Cohort not found"}), 404

            already = conn.execute(
                "SELECT 1 FROM cohort_enrollments WHERE cohort_id=? AND intern_id=?",
                (cohort_id, intern["id"])
            ).fetchone()
            if already:
                return jsonify({"status": "error", "message": "Already enrolled in this cohort"}), 400

            cap_val = cohort["capacity"] if "capacity" in cohort.keys() else cohort["max_capacity"] if "max_capacity" in cohort.keys() else 0
            max_cap = int(cap_val or 0)
            cursor = conn.execute(
                """
                INSERT INTO cohort_enrollments (cohort_id, intern_id)
                SELECT ?, ?
                WHERE ? = 0 OR (SELECT COUNT(*) FROM cohort_enrollments WHERE cohort_id=?) < ?
                """,
                (cohort_id, intern["id"], max_cap, cohort_id, max_cap)
            )
            if cursor.rowcount == 0:
                return jsonify({"status": "error", "message": "This cohort is full"}), 400

            conn.commit()
            return jsonify({"status": "success", "message": "Successfully enrolled in cohort"})
    except Exception as e:
        log_error("cohort-enroll", e)
        return jsonify({"status": "error", "message": "Failed to enroll"}), 500


@enrollment_bp.route("/attendance/ping", methods=["POST"])
def attendance_ping():
    """Lightweight client beacon to record active attendance."""
    with get_db() as conn:
        intern = AuthService.current_intern(conn)
    if not intern:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    try:
        now = now_str()
        today = now.split()[0]
        with get_db() as conn:
            existing = conn.execute(
                "SELECT id FROM attendance WHERE intern_id=? AND date=?",
                (intern["id"], today)
            ).fetchone()
            if not existing:
                conn.execute(
                    "INSERT INTO attendance (intern_id, date, timestamp, status) VALUES (?, ?, ?, 'Present')",
                    (intern["id"], today, now)
                )
                conn.commit()
        return jsonify({"status": "success", "attendance": "recorded"})
    except Exception as e:
        log_error("attendance-ping", e)
        return jsonify({"status": "error", "message": "Attendance logging failed"}), 500


@enrollment_bp.route("/launchpad", methods=["GET"])
def launchpad_checkout():
    """Public landing page for DBERT Launchpad (2-month course track + AI tutor)."""
    from flask import render_template
    return render_template("program.html", program_name="launchpad", title="DBERT Launchpad Program")


@enrollment_bp.route("/accelerate", methods=["GET"])
def accelerate_checkout():
    """Public landing page for DBERT Accelerate (Live Project Sprints)."""
    from flask import render_template
    return render_template("program.html", program_name="accelerate", title="DBERT Accelerate Sprints")

