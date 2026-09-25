"""
routes/applications.py - Applications Routing Blueprint
Fulfills Phase 23 (Monolith Modularization) of INTERNSHIPPORTAL4_LOCAL_AI_AGENT_MASTER_PLAN.md

Endpoints:
- GET /intern/my-applications
"""
import json
from flask import Blueprint, jsonify
from services.auth_service import AuthService
from app import (
    get_db, current_intern, row_to_dict, _post_path,
    _interview_state_for_post, INTERVIEW_MAX_ATTEMPTS,
    INTERVIEW_ENABLED, log_error
)

applications_bp = Blueprint("applications", __name__)


@applications_bp.route("/intern/my-applications", methods=["GET"])
def intern_my_applications():
    """Returns the logged-in intern's job/internship applications and statuses."""
    try:
        with get_db() as conn:
            intern = AuthService.current_intern(conn)
        if not intern:
            return jsonify({"status": "error", "message": "Unauthorized"}), 401
        intern_email = (intern.get("email") or "").strip().lower()
        with get_db() as conn:
            rows = conn.execute(
                "SELECT pa.id, pa.status, pa.comment, pa.created_at, pa.decision_note, "
                "pa.needed_certs_json, p.id AS post_id, p.title AS post_title, "
                "p.post_type, p.slug, co.id AS company_id, co.name AS company_name "
                "FROM post_applications pa JOIN posts p ON p.id = pa.post_id "
                "JOIN companies co ON co.id = p.company_id "
                "WHERE (pa.intern_id=? OR (pa.email IS NOT NULL AND LOWER(pa.email)=LOWER(?))) ORDER BY pa.id DESC",
                (intern["id"], intern_email),
            ).fetchall()
            out = []
            for r in rows:
                d = row_to_dict(r)
                try:
                    d["needed_certs"] = json.loads(d.pop("needed_certs_json") or "[]")
                except (ValueError, TypeError):
                    d["needed_certs"] = []
                d["post_path"] = _post_path({"post_type": d["post_type"], "slug": d["slug"], "id": d["post_id"]})
                ivr = conn.execute(
                    "SELECT status, attempt_no FROM interviews WHERE email=? AND post_id=? "
                    "ORDER BY id DESC LIMIT 1", (intern["email"], d["post_id"])).fetchone()
                iv = row_to_dict(ivr) if ivr else None
                attempts_used, locked, cooling_until, cooling_passed = _interview_state_for_post(
                    conn, intern["email"], intern, d["post_id"])
                d["interview"] = {
                    "status": iv.get("status") if iv else "not_started",
                    "in_progress": bool(iv and iv.get("status") == "in_progress"),
                    "attempts_used": attempts_used,
                    "max_attempts": INTERVIEW_MAX_ATTEMPTS,
                    "locked": locked,
                    "cooling_until": cooling_until,
                    "can_start": bool(INTERVIEW_ENABLED and not locked
                                      and attempts_used < INTERVIEW_MAX_ATTEMPTS and cooling_passed),
                }
                out.append(d)
        return jsonify({"status": "success", "applications": out, "tutor_base": "https://internship.dbert.online"})
    except Exception as e:
        log_error("intern-my-applications", e)
        return jsonify({"status": "error", "message": "Error"}), 500
