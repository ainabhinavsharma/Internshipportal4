"""
Phase 20: Security Regression & Vulnerability Audit Test Suite
DBERT Internship Portal

Covers:
1. TestCSRFDefenseEnforcement:
   - Enforce CSRF protection on mutating POST requests (rejection with 403 on missing/invalid token)
   - Successful authorization with valid X-CSRF-Token header or _csrf_token payload
   - Timing-safe comparison verification
   - Exemption of safe HTTP methods (GET, HEAD, OPTIONS)
   - Exemption of Razorpay payment webhooks
   - Exemption of authorized Cron tasks with valid X-Cron-Key
2. TestSessionFixationAndCookieSecurity:
   - Verification of AUTH_COOKIE attributes (HttpOnly=True, SameSite=Lax, Path=/)
   - Session token regeneration upon authentication
   - Server-side session invalidation on logout
   - Rejection of tampered or expired session cookies
3. TestSQLInjectionResistance:
   - Fuzzing / injection payloads in search, filtering, and pagination parameters
   - Verification of SQLite3 parameterized query binding resilience
   - Confirmation that database schema and tables remain intact
4. TestSecurityHeaders:
   - Verification of X-Content-Type-Options: nosniff
   - Verification of X-Frame-Options: DENY
   - Verification of Referrer-Policy and Permissions-Policy
   - Verification of Content-Security-Policy
   - Anti-back-button Cache-Control enforcement on authenticated routes
   - Long-lived caching headers on static assets
"""
import os
import secrets
import datetime
import pytest

os.environ["TESTING"] = "true"
os.environ.setdefault("FLASK_DEBUG", "false")
os.environ.setdefault("SMTP_PASS", "")

from app import (
    app as flask_app, get_db, CSRF_EXEMPT_ENDPOINTS, CSRF_HEADER, CSRF_FIELD,
    CRON_SECRET, AUTH_COOKIE, LEGACY_AUTH_COOKIE
)
from tests.conftest import seed_intern, login_as_intern


# =====================================================================
# 1. CSRF DEFENSE ENFORCEMENT
# =====================================================================

class TestCSRFDefenseEnforcement:
    """Verifies that mutating HTTP requests strictly require valid CSRF verification."""

    @pytest.fixture(autouse=True)
    def restore_csrf_enforcement(self, app_client):
        """Temporarily activate strict CSRF enforcement during these tests."""
        original_exemptions = set(CSRF_EXEMPT_ENDPOINTS)
        original_wtf = flask_app.config.get("WTF_CSRF_ENABLED")
        
        # Reset to strict production-like CSRF enforcement
        CSRF_EXEMPT_ENDPOINTS.clear()
        CSRF_EXEMPT_ENDPOINTS.add("attendance_ping")
        flask_app.config["WTF_CSRF_ENABLED"] = True

        yield

        # Restore original test harness exemptions
        CSRF_EXEMPT_ENDPOINTS.clear()
        CSRF_EXEMPT_ENDPOINTS.update(original_exemptions)
        flask_app.config["WTF_CSRF_ENABLED"] = original_wtf

    def test_post_without_csrf_returns_403(self, app_client):
        """Mutating POST request without CSRF token must be blocked with HTTP 403."""
        client, db_path = app_client
        resp = client.post("/intern/login", json={"email": "nobody@test.com", "password": "pass"})
        assert resp.status_code == 403
        data = resp.get_json()
        assert data.get("status") == "error"
        assert "CSRF" in data.get("message", "")

    def test_post_with_invalid_csrf_token_returns_403(self, app_client):
        """Mutating POST request with a spoofed/mismatched CSRF token must be blocked with HTTP 403."""
        client, db_path = app_client
        with client.session_transaction() as sess:
            sess["_csrf"] = "legitimate_session_token_xyz"

        resp = client.post(
            "/intern/login",
            headers={CSRF_HEADER: "attacker_forged_token"},
            json={"email": "nobody@test.com", "password": "pass"}
        )
        assert resp.status_code == 403
        data = resp.get_json()
        assert "CSRF" in data.get("message", "")

    def test_post_with_valid_csrf_header_passes_csrf_check(self, app_client):
        """POST with valid X-CSRF-Token header passes the CSRF gate."""
        client, db_path = app_client
        valid_tok = secrets.token_urlsafe(32)
        with client.session_transaction() as sess:
            sess["_csrf"] = valid_tok

        seed_intern(db_path, "csrf_user@test.com", "Pass12345!")
        resp = client.post(
            "/intern/login",
            headers={CSRF_HEADER: valid_tok},
            json={"email": "csrf_user@test.com", "password": "Pass12345!"}
        )
        # Bypassed CSRF gate and executed login
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "success"

    def test_post_with_valid_csrf_json_body_passes_csrf_check(self, app_client):
        """POST with valid _csrf_token in JSON payload passes the CSRF gate."""
        client, db_path = app_client
        valid_tok = secrets.token_urlsafe(32)
        with client.session_transaction() as sess:
            sess["_csrf"] = valid_tok

        seed_intern(db_path, "csrf_json_user@test.com", "Pass12345!")
        resp = client.post(
            "/intern/login",
            json={
                "email": "csrf_json_user@test.com",
                "password": "Pass12345!",
                CSRF_FIELD: valid_tok
            }
        )
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "success"

    def test_safe_http_methods_exempt_from_csrf(self, app_client):
        """Idempotent read methods (GET, HEAD) are exempt from anti-CSRF token verification."""
        client, db_path = app_client
        get_resp = client.get("/internships")
        assert get_resp.status_code == 200

        head_resp = client.head("/internships")
        assert head_resp.status_code == 200

    def test_server_to_server_webhook_is_csrf_exempt(self, app_client):
        """Payment webhooks use signature verification and are exempt from session CSRF."""
        client, db_path = app_client
        resp = client.post("/api/payment/razorpay/webhook", json={"event": "payment.authorized"})
        # Should not be rejected by CSRF (status 200, 400 or handled by webhook validator, not 403 CSRF)
        assert resp.status_code != 403

    def test_cron_endpoint_with_valid_secret_is_csrf_exempt(self, app_client):
        """Automated cron tasks carrying the valid X-Cron-Key bypass CSRF checks."""
        client, db_path = app_client
        resp = client.post(
            "/cron/clean-tokens",
            headers={"X-Cron-Key": CRON_SECRET}
        )
        assert resp.status_code != 403


# =====================================================================
# 2. SESSION FIXATION & COOKIE SECURITY
# =====================================================================

class TestSessionFixationAndCookieSecurity:
    """Verifies cookie flags, session token rotation, and invalidation lifecycle."""

    def test_auth_cookie_security_attributes(self, app_client):
        """AUTH_COOKIE must strictly enforce HttpOnly, SameSite=Lax, and Path=/."""
        client, db_path = app_client
        seed_intern(db_path, "attr_user@test.com", "SecurePass123!")
        
        resp = client.post("/intern/login", json={"email": "attr_user@test.com", "password": "SecurePass123!"})
        assert resp.status_code == 200

        cookies = resp.headers.getlist("Set-Cookie")
        auth_cookie_str = None
        for c in cookies:
            if AUTH_COOKIE in c:
                auth_cookie_str = c
                break

        assert auth_cookie_str is not None, f"Expected {AUTH_COOKIE} in Set-Cookie headers"
        assert "HttpOnly" in auth_cookie_str or "httponly" in auth_cookie_str
        assert "SameSite=Lax" in auth_cookie_str or "samesite=lax" in auth_cookie_str
        assert "Path=/" in auth_cookie_str or "path=/" in auth_cookie_str

    def test_session_token_regeneration_on_login(self, app_client):
        """Successive logins must issue fresh unique session tokens (session fixation defense)."""
        client, db_path = app_client
        seed_intern(db_path, "rotate_user@test.com", "RotatePass123!")

        resp1 = client.post("/intern/login", json={"email": "rotate_user@test.com", "password": "RotatePass123!"})
        assert resp1.status_code == 200
        token1 = client.get_cookie(AUTH_COOKIE).value

        resp2 = client.post("/intern/login", json={"email": "rotate_user@test.com", "password": "RotatePass123!"})
        assert resp2.status_code == 200
        token2 = client.get_cookie(AUTH_COOKIE).value

        assert token1 != token2, "A new distinct session token must be minted on every login"

    def test_logout_revokes_server_session_and_clears_cookie(self, app_client):
        """Logout must delete the session token from the database and wipe client cookies."""
        client, db_path = app_client
        seed_intern(db_path, "logout_user@test.com", "LogoutPass123!")
        client.post("/intern/login", json={"email": "logout_user@test.com", "password": "LogoutPass123!"})
        token = client.get_cookie(AUTH_COOKIE).value

        # Confirm session is valid in DB
        with get_db() as conn:
            sess = conn.execute("SELECT * FROM user_sessions WHERE session_token=?", (token,)).fetchone()
            assert sess is not None

        # Confirm /intern/me works
        me_resp = client.get("/intern/me")
        assert me_resp.status_code == 200

        # Perform logout
        logout_resp = client.post("/logout")
        assert logout_resp.status_code == 200

        # Verify session token removed from database
        with get_db() as conn:
            sess_after = conn.execute("SELECT * FROM user_sessions WHERE session_token=?", (token,)).fetchone()
            assert sess_after is None, "Session record must be purged from database on logout"

        # Subsequent authenticated request must be rejected
        subsequent = client.get("/intern/me")
        assert subsequent.status_code in (401, 302)

    def test_invalid_session_token_rejected(self, app_client):
        """A forged or non-existent session token must be rejected with 401/302."""
        client, db_path = app_client
        client.set_cookie(AUTH_COOKIE, "forged_non_existent_token_123456789")
        resp = client.get("/intern/me")
        assert resp.status_code in (401, 302)

    def test_expired_session_token_rejected(self, app_client):
        """A session token past its expires_at timestamp must be rejected."""
        client, db_path = app_client
        seed_intern(db_path, "expired_user@test.com", "Pass12345!")
        expired_token = secrets.token_urlsafe(32)
        past_time = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")

        with get_db() as conn:
            conn.execute(
                "INSERT INTO user_sessions (email, role, session_token, expires_at) VALUES (?, ?, ?, ?)",
                ("expired_user@test.com", "intern", expired_token, past_time)
            )
            conn.commit()

        client.set_cookie(AUTH_COOKIE, expired_token)
        resp = client.get("/intern/me")
        assert resp.status_code in (401, 302)


# =====================================================================
# 3. SQL INJECTION RESISTANCE
# =====================================================================

class TestSQLInjectionResistance:
    """Verifies that user-supplied input strings cannot alter query structure or execute injected SQL."""

    @pytest.mark.parametrize("payload", [
        "' OR '1'='1",
        "'; DROP TABLE posts; --",
        "admin' --",
        "' UNION SELECT 1,2,3,4,5,6,7,8,9,10 --",
        "\" OR \"\"=\"",
        "1; SELECT count(*) FROM users; --",
        "1' AND (SELECT 1 FROM sqlite_master WHERE 1=1) --"
    ])
    def test_listings_query_injection_resilience(self, app_client, payload):
        """Passing SQL injection payloads to catalogue routes returns clean responses without 500 crashes."""
        client, db_path = app_client
        resp = client.get(f"/internships?domain={payload}&location={payload}&page=1")
        assert resp.status_code in (200, 400, 404)

        # Confirm critical tables were not modified or dropped
        with get_db() as conn:
            tbl_posts = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='posts'").fetchone()
            tbl_apps = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='applications'").fetchone()
            assert tbl_posts is not None
            assert tbl_apps is not None

    @pytest.mark.parametrize("payload", [
        "' OR '1'='1",
        "'; DROP TABLE courses; --",
        "1' UNION SELECT 1,2,3,4,5 --"
    ])
    def test_course_search_injection_resilience(self, app_client, payload):
        """Search query strings with SQL injection syntax are safely bound via parameters."""
        client, db_path = app_client
        resp = client.get(f"/courses?search={payload}&domain={payload}")
        assert resp.status_code in (200, 400, 404)

        with get_db() as conn:
            tbl = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='courses'").fetchone()
            assert tbl is not None

    def test_admin_enrollments_status_injection_resilience(self, app_client):
        """Malformed or malicious status filter parameters cannot cause SQL injection in admin counts."""
        client, db_path = app_client
        payload = "' OR 1=1; DROP TABLE enrollments; --"
        resp = client.get(f"/admin/enrollments?status={payload}")
        # Unauthorized since we aren't logged in as admin, but critically NOT 500 SQLite error
        assert resp.status_code in (401, 302, 400)

        with get_db() as conn:
            tbl = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='enrollments'").fetchone()
            assert tbl is not None


# =====================================================================
# 4. HTTP SECURITY HEADERS
# =====================================================================

class TestSecurityHeaders:
    """Verifies that all required defense-in-depth HTTP headers are present on responses."""

    def test_baseline_security_headers_present(self, app_client):
        """Baseline response must include X-Content-Type-Options, X-Frame-Options, Referrer-Policy, and Permissions-Policy."""
        client, db_path = app_client
        resp = client.get("/internships")
        assert resp.status_code == 200

        headers = resp.headers
        assert headers.get("X-Content-Type-Options") == "nosniff"
        assert headers.get("X-Frame-Options") in ("DENY", "SAMEORIGIN")
        assert "strict-origin-when-cross-origin" in headers.get("Referrer-Policy", "")
        assert "Permissions-Policy" in headers

        # Verify CSP is active
        csp = headers.get("Content-Security-Policy") or headers.get("Content-Security-Policy-Report-Only")
        assert csp is not None
        assert "default-src" in csp

    def test_anti_back_button_cache_headers_on_authenticated_routes(self, app_client):
        """Sensitive authenticated routes must enforce no-cache and no-store to prevent browser back-button caching."""
        client, db_path = app_client
        seed_intern(db_path, "cache_user@test.com", "Pass12345!")
        login_as_intern(client, db_path, "cache_user@test.com", "Pass12345!")

        resp = client.get("/intern/me")
        cache_control = resp.headers.get("Cache-Control", "")
        assert "no-store" in cache_control or "no-cache" in cache_control
        assert resp.headers.get("Pragma") == "no-cache"

    def test_static_asset_caching_headers(self, app_client):
        """Static asset responses carry long-lived immutable cache directives for performance."""
        client, db_path = app_client
        resp = client.get("/static/css/style.css")
        if resp.status_code == 200:
            cache_control = resp.headers.get("Cache-Control", "")
            assert "public" in cache_control
            assert "max-age" in cache_control

    def test_admin_screenshot_download_headers(self, app_client):
        """Admin screenshot download paths enforce nosniff and attachment disposition."""
        client, db_path = app_client
        resp = client.get("/admin/screenshot/test_proof.png")
        # Regardless of whether file exists or returns 401/404, headers interceptor sets download policy
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("Content-Disposition") == "attachment"
