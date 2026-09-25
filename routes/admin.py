"""
routes/admin.py - Administration Routing Blueprint
Fulfills Phase 23 (Monolith Modularization) of INTERNSHIPPORTAL4_LOCAL_AI_AGENT_MASTER_PLAN.md

Endpoints:
- POST /admin/companies/approve
- POST /admin/companies/suspend
- GET  /admin/telemetry
- GET  /admin/learning-analytics
"""
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request, redirect, render_template
from services.auth_service import AuthService
from services.telemetry_service import get_telemetry_snapshot
from app import (
    get_db, require_admin, require_role, now_str, clean_text
)

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/admin/companies/approve", methods=["POST"])
def admin_company_approve():
    """Approves or unapproves a partner company."""
    with get_db() as conn:
        admin_user = AuthService.require_admin(conn)
    if not admin_user:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    data = request.get_json(force=True, silent=True) or {}
    cid = data.get("company_id")
    approve = 1 if data.get("approve", True) else 0

    with get_db() as conn:
        conn.execute(
            "UPDATE companies SET is_approved=?, updated_at=? WHERE id=?",
            (approve, now_str(), cid)
        )
        conn.commit()
    return jsonify({"status": "success", "is_approved": approve})


@admin_bp.route("/admin/companies/suspend", methods=["POST"])
def admin_company_suspend():
    """Suspends or activates a partner company account."""
    with get_db() as conn:
        admin_user = AuthService.require_admin(conn)
    if not admin_user:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    data = request.get_json(force=True, silent=True) or {}
    cid = data.get("company_id")
    active = 0 if data.get("suspend", True) else 1

    with get_db() as conn:
        conn.execute(
            "UPDATE companies SET is_active=?, updated_at=? WHERE id=?",
            (active, now_str(), cid)
        )
        conn.commit()
    return jsonify({"status": "success", "is_active": active})


@admin_bp.route("/admin/telemetry", methods=["GET"])
def admin_telemetry():
    """Real-time observability and telemetry metrics endpoint."""
    with get_db() as conn:
        admin_user = AuthService.require_admin(conn)
    if not admin_user:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    return jsonify({
        "status": "success",
        "metrics": get_telemetry_snapshot()
    })
