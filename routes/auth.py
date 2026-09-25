"""
routes/auth.py - Authentication & Session Routing Blueprint
Fulfills Phase 23 (Monolith Modularization) of INTERNSHIPPORTAL4_LOCAL_AI_AGENT_MASTER_PLAN.md

Endpoints:
- /intern/login
- /company/login
- /mentor/login
- /staff/login
- /admin/login
- /logout
- /check-email
- /api/auth/status
"""
from flask import Blueprint, jsonify, request, redirect, session, make_response
from services.auth_service import AuthService
from app import (
    get_db, clean_text, get_client_ip, rate_check, log_abuse,
    login_locked, record_login_fail, clear_login_fails,
    link_device_to_email, _set_session_cookie, _clear_session_cookie,
    _safe_portal_next, log_error, is_valid_phone, too_many,
    RL_LOGIN_IP, RL_LOGIN_EMAIL, RL_CHECKEMAIL_IP
)

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/api/auth/status", methods=["GET"])
def api_auth_status():
    """Returns the current authenticated session status across roles."""
    with get_db() as conn:
        user = AuthService.get_current_user(conn)
    if not user:
        return jsonify({"authenticated": False, "role": None})
    return jsonify({
        "authenticated": True,
        "email": user.get("email"),
        "role": user.get("role")
    })


@auth_bp.route("/intern/login", methods=["POST"])
def intern_login():
    """Authenticates intern via email or phone."""
    try:
        data = request.get_json(force=True) or {}
        input_cred = clean_text(data.get("email")).strip()
        email = input_cred.lower()
        password = clean_text(data.get("password"))
        if not input_cred or not password:
            return jsonify({"status": "error", "message": "Email/Mobile and password required."}), 400

        ip = get_client_ip()
        allowed, ra = rate_check(f"login:intern:ip:{ip}", *RL_LOGIN_IP)
        if not allowed:
            log_abuse(ip, "/intern/login", f"login:intern:ip:{ip}", "rate_limit", email)
            return too_many(ra)

        with get_db() as conn:
            if is_valid_phone(input_cred):
                user = conn.execute(
                    "SELECT * FROM intern_accounts WHERE phone=? AND is_active=1 LIMIT 1", (input_cred,)
                ).fetchone()
                if user:
                    email = user["email"].lower()
            else:
                user = conn.execute(
                    "SELECT * FROM intern_accounts WHERE email=? AND is_active=1 LIMIT 1", (email,)
                ).fetchone()

            locked, _ = login_locked(email)
            if locked:
                log_abuse(ip, "/intern/login", f"login_locked:{email}", "login_lockout", email)
                return jsonify({"status": "error", "message": "Invalid credentials."}), 401

            if not user or int(user["password_set"] or 0) != 1 or not AuthService.verify_password(user["password_hash"], password):
                record_login_fail(email)
                return jsonify({"status": "error", "message": "Invalid credentials. (If you have a legacy account without a password, use Forgot Password)"}), 401

            if AuthService.is_legacy_hash(user["password_hash"]):
                AuthService.migrate_password_hash(conn, "intern_accounts", email, password)

            clear_login_fails(email)
            token = AuthService.create_session(conn, email, "intern")

        link_device_to_email(data.get("visitor_id"), email)

        if int(user["signup_stage"] or 3) < 3:
            session.pop("post_login_return_to", None)
            session.pop("post_login_next", None)
            session.pop("next", None)
            resp = make_response(jsonify({
                "status": "success",
                "message": "Welcome back — let's finish setting up your account.",
                "redirect": "/#signup",
            }))
            _set_session_cookie(resp, token)
            return resp

        login_redirect = "/profile"
        if session.pop("post_login_return_to", None) == "tutor":
            login_redirect = session.pop("post_login_next", None) or "/tasks"
        session.pop("post_login_next", None)

        pending_next = _safe_portal_next(session.pop("next", None))
        if pending_next and login_redirect == "/profile":
            login_redirect = pending_next

        resp = make_response(jsonify({"status": "success", "message": "Login successful.", "redirect": login_redirect}))
        _set_session_cookie(resp, token)
        return resp
    except Exception as e:
        log_error("intern-login", e)
        return jsonify({"status": "error", "message": "Error"}), 500


@auth_bp.route("/logout", methods=["GET", "POST"])
def logout():
    """Logs out user across all roles, deletes session token in DB, and clears cookies."""
    token = AuthService.get_session_token_from_request()
    if token:
        with get_db() as conn:
            AuthService.invalidate_session(conn, token)
    resp = redirect("/")
    _clear_session_cookie(resp)
    return resp
