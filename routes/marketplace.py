"""
routes/marketplace.py - Marketplace & Job Board Routing Blueprint
Fulfills Phase 23 (Monolith Modularization) of INTERNSHIPPORTAL4_LOCAL_AI_AGENT_MASTER_PLAN.md

Endpoints:
- POST /company/posts
- POST /company/posts/<int:post_id>/publish
- POST /company/posts/<int:post_id>/unpublish
- POST /company/posts/<int:post_id>/delete
- POST /posts/<int:post_id>/apply
"""
import json
from datetime import date, timedelta
from flask import Blueprint, jsonify, request
from services.auth_service import AuthService
from services.marketplace_service import MarketplaceService
from app import (
    get_db, clean_text, current_company, current_intern, row_to_dict,
    now_str, log_error, _int_or_none, _post_slugify, _post_path,
    POST_TYPES, VALID_DOMAINS
)

marketplace_bp = Blueprint("marketplace", __name__)


@marketplace_bp.route("/company/posts", methods=["POST"])
def company_post_save():
    """Saves or updates a draft/published job or internship post."""
    with get_db() as conn:
        company = AuthService.current_company(conn)
    if not company:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    data = request.get_json(force=True, silent=True) or {}
    post_type = clean_text(data.get("post_type"))
    domain = clean_text(data.get("domain"))
    title = clean_text(data.get("title"))

    if post_type not in POST_TYPES:
        return jsonify({"status": "error", "message": "Choose job or internship."}), 400
    if domain not in VALID_DOMAINS:
        return jsonify({"status": "error", "message": "Choose a valid domain."}), 400
    if not title:
        return jsonify({"status": "error", "message": "Title is required."}), 400

    is_unpaid = 1 if data.get("is_unpaid") else 0
    stipend_min = None if is_unpaid else _int_or_none(data.get("stipend_min"))
    stipend_max = None if is_unpaid else _int_or_none(data.get("stipend_max"))
    pay_period = "" if is_unpaid else clean_text(data.get("pay_period"))
    apply_by = clean_text(data.get("apply_by")) or (date.today() + timedelta(days=15)).isoformat()

    vals = (
        post_type, domain, title, _post_slugify(title),
        (data.get("description") or "").strip(),
        (data.get("responsibilities") or "").strip(),
        clean_text(data.get("skills")),
        clean_text(data.get("location")),
        clean_text(data.get("work_mode")),
        stipend_min, stipend_max, pay_period, is_unpaid,
        clean_text(data.get("duration")),
        _int_or_none(data.get("openings")) or 1,
        apply_by,
        json.dumps(data.get("certifications") or []),
        (data.get("eligibility") or "").strip(),
    )
    post_id = data.get("post_id")
    with get_db() as conn:
        if post_id:
            owns = conn.execute(
                "SELECT id FROM posts WHERE id=? AND company_id=? AND status != 'deleted'",
                (post_id, company["id"])
            ).fetchone()
            if not owns:
                return jsonify({"status": "error", "message": "Not found"}), 404

            conn.execute(
                "UPDATE posts SET post_type=?,domain=?,title=?,slug=?,description=?,"
                "responsibilities=?,skills=?,location=?,work_mode=?,stipend_min=?,"
                "stipend_max=?,pay_period=?,is_unpaid=?,duration=?,openings=?,apply_by=?,"
                "certifications_json=?,eligibility=?,updated_at=? WHERE id=? AND company_id=?",
                (*vals, now_str(), post_id, company["id"])
            )
            conn.commit()
            return jsonify({"status": "success", "post_id": post_id})

        cur = conn.execute(
            "INSERT INTO posts (company_id,post_type,domain,title,slug,description,"
            "responsibilities,skills,location,work_mode,stipend_min,stipend_max,pay_period,"
            "is_unpaid,duration,openings,apply_by,certifications_json,eligibility,status,"
            "created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'draft',?,?)",
            (company["id"], *vals, now_str(), now_str())
        )
        conn.commit()
        return jsonify({"status": "success", "post_id": cur.lastrowid})


@marketplace_bp.route("/company/posts/<int:post_id>/publish", methods=["POST"])
def company_post_publish(post_id):
    """Publishes a draft post with company approval check and quota limit."""
    with get_db() as conn:
        company = AuthService.current_company(conn)
    if not company:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    if not company["is_approved"] or not company["is_active"]:
        return jsonify({"status": "error", "message": "Company account is pending approval."}), 403

    with get_db() as conn:
        post = conn.execute("SELECT * FROM posts WHERE id=? AND company_id=?", (post_id, company["id"])).fetchone()
        if not post:
            return jsonify({"status": "error", "message": "Not found"}), 404
        if not MarketplaceService.can_company_create_post(conn, company["id"], max_posts=3):
            return jsonify({"status": "error", "message": "Maximum active post quota reached (3 active posts)."}), 400

        conn.execute("UPDATE posts SET status='published', updated_at=? WHERE id=?", (now_str(), post_id))
        conn.commit()
        return jsonify({"status": "success", "message": "Post published"})


@marketplace_bp.route("/company/posts/<int:post_id>/unpublish", methods=["POST"])
def company_post_unpublish(post_id):
    """Unpublishes an active post back to draft."""
    with get_db() as conn:
        company = AuthService.current_company(conn)
    if not company:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    with get_db() as conn:
        conn.execute(
            "UPDATE posts SET status='draft', updated_at=? WHERE id=? AND company_id=?",
            (now_str(), post_id, company["id"])
        )
        conn.commit()
        return jsonify({"status": "success", "message": "Post unpublished"})


@marketplace_bp.route("/company/posts/<int:post_id>/delete", methods=["POST"])
def company_post_delete(post_id):
    """Marks a post as deleted."""
    with get_db() as conn:
        company = AuthService.current_company(conn)
    if not company:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    with get_db() as conn:
        conn.execute(
            "UPDATE posts SET status='deleted', updated_at=? WHERE id=? AND company_id=?",
            (now_str(), post_id, company["id"])
        )
        conn.commit()
        return jsonify({"status": "success", "message": "Post deleted"})
