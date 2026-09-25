"""
routes/company.py - Company Portal & Candidate Review Routing Blueprint
Fulfills Phase 23 (Monolith Modularization) of INTERNSHIPPORTAL4_LOCAL_AI_AGENT_MASTER_PLAN.md

Endpoints:
- POST /company/applications/<int:app_id>/status
"""
import json
from flask import Blueprint, jsonify, request
from services.auth_service import AuthService
from app import (
    get_db, clean_text, row_to_dict, now_str, log_error,
    current_company, APPLICATION_STATUSES, APP_STATUS_PENDING_CERTS,
    _post_required_certs, _certifiable_course_ids
)

company_bp = Blueprint("company", __name__)


@company_bp.route("/company/applications/<int:app_id>/status", methods=["POST"])
def company_app_status(app_id):
    """Updates candidate status for an application belonging to the logged-in company."""
    with get_db() as conn:
        company = AuthService.current_company(conn)
    if not company:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    data = request.get_json(force=True, silent=True) or {}
    new_status = clean_text(data.get("status"))
    if new_status not in APPLICATION_STATUSES:
        return jsonify({"status": "error", "message": "Invalid status."}), 400

    is_cert_gate = new_status == APP_STATUS_PENDING_CERTS
    needed_certs = []
    note = clean_text(data.get("note")) if is_cert_gate else ""

    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT pa.id, pa.status AS old_status, pa.intern_id, p.title AS post_title, "
                "p.certifications_json, a.name AS intern_name, a.email AS intern_email "
                "FROM post_applications pa JOIN posts p ON p.id = pa.post_id "
                "JOIN intern_accounts a ON a.id = pa.intern_id "
                "WHERE pa.id=? AND p.company_id=?", (app_id, company["id"]),
            ).fetchone()
            if not row:
                return jsonify({"status": "error", "message": "Not found"}), 404

            r = row_to_dict(row)
            if is_cert_gate:
                if isinstance(data.get("needed_certs"), list):
                    needed_certs = _post_required_certs({"certifications_json": json.dumps(data["needed_certs"])})
                    certifiable_ids = _certifiable_course_ids()
                    needed_certs = [c for c in needed_certs if c["course_id"] in certifiable_ids]
                else:
                    required = _post_required_certs({"certifications_json": r["certifications_json"]})
                    certifiable_ids = _certifiable_course_ids()
                    required = [c for c in required if c["course_id"] in certifiable_ids]
                    earned_ids = {e["course_id"] for e in conn.execute(
                        "SELECT course_id FROM intern_certificates WHERE intern_id=? OR (email IS NOT NULL AND LOWER(email)=LOWER(?))",
                        (r["intern_id"], r.get("intern_email") or "")).fetchall()}
                    needed_certs = [c for c in required if c["course_id"] not in earned_ids]

                if not needed_certs:
                    return jsonify({
                        "status": "error",
                        "message": "Cannot set Pending Certifications when no course certifications are required or missing."
                    }), 400

            conn.execute(
                "UPDATE post_applications SET status=?, needed_certs_json=?, decision_note=?, updated_at=? WHERE id=?",
                (new_status, json.dumps(needed_certs), note, now_str(), app_id)
            )
            conn.commit()

        return jsonify({"status": "success", "new_status": new_status, "needed_certs": needed_certs})
    except Exception as e:
        log_error("company-app-status", e)
        return jsonify({"status": "error", "message": "Failed to update status"}), 500
