"""
routes/intern.py - Intern Portal & Certificate Routing Blueprint
Fulfills Phase 23 (Monolith Modularization) of INTERNSHIPPORTAL4_LOCAL_AI_AGENT_MASTER_PLAN.md

Endpoints:
- GET /intern/certificates
"""
from flask import Blueprint, jsonify
from services.auth_service import AuthService
from services.certificate_service import CertificateService
from app import get_db, current_intern, log_error

intern_bp = Blueprint("intern", __name__)


@intern_bp.route("/intern/certificates", methods=["GET"])
def intern_certificates_json():
    """Returns earned certificates for the logged-in intern."""
    try:
        with get_db() as conn:
            intern = AuthService.current_intern(conn)
        if not intern:
            return jsonify({"status": "error", "message": "Unauthorized"}), 401

        with get_db() as conn:
            email = (intern.get("email") or "").strip().lower()
            certs = CertificateService.get_intern_certificates(conn, intern["id"], email)
            for d in certs:
                d["download_url"] = d.get("url") or f"/portal/certificate/{d['cert_id']}"
        return jsonify({"status": "success", "certificates": certs})
    except Exception as e:
        log_error("intern-certificates", e)
        return jsonify({"status": "error", "message": "Error"}), 500
