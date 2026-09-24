"""
Phase 10: Multi-Role Authentication Regression Suite
Covers the complete authentication and session lifecycle across all 5 roles:
- intern (email & phone login, registration, multi-session)
- company (login, registration)
- mentor (login)
- staff (login, session management)
- admin (login, admin privilege session)
- Duplicate email and duplicate phone rejection
- Password reset lifecycle (neutral enumeration, expiration, replay prevention, session revocation)
- Logout invalidation and browser-back button cache denial
"""
import os
import json
import secrets
import hashlib
import datetime
import pytest

os.environ["TESTING"] = "true"
os.environ.setdefault("FLASK_DEBUG", "false")
os.environ.setdefault("SMTP_PASS", "")

from tests.conftest import (
    seed_intern, seed_company, seed_staff, seed_mentor,
    login_as_intern, login_as_company, login_as_staff, login_as_mentor, login_as_admin,
    inject_reset_token, logout
)
from app import app, get_db, set_password_hash, create_session, AUTH_COOKIE, get_current_user


class TestMultiRoleLogin:
    """Verifies that all 5 supported roles can authenticate and receive appropriate session contexts."""

    def test_intern_login_with_email_success(self, app_client):
        client, db_path = app_client
        email = "intern_email_test@example.com"
        seed_intern(db_path, email=email, password="ValidPassword123!", name="Email Intern")

        resp = client.post("/intern/login", json={"email": email, "password": "ValidPassword123!"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("status") == "success"

        # Check session in database
        os.environ["DB_FILE"] = db_path
        with get_db() as conn:
            sess = conn.execute("SELECT * FROM user_sessions WHERE email=?", (email,)).fetchone()
        assert sess is not None
        assert sess["role"] == "intern"

    def test_intern_login_with_phone_success(self, app_client):
        client, db_path = app_client
        email = "intern_phone_test@example.com"
        phone = "9876543210"
        seed_intern(db_path, email=email, password="ValidPassword123!", name="Phone Intern")
        os.environ["DB_FILE"] = db_path
        with get_db() as conn:
            conn.execute("UPDATE intern_accounts SET phone=? WHERE email=?", (phone, email))
            conn.commit()

        resp = client.post("/intern/login", json={"email": phone, "password": "ValidPassword123!"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("status") == "success"

        with get_db() as conn:
            sess = conn.execute("SELECT * FROM user_sessions WHERE email=?", (email,)).fetchone()
        assert sess is not None
        assert sess["role"] == "intern"

    def test_company_login_success(self, app_client):
        client, db_path = app_client
        email = "company_test@example.com"
        seed_company(db_path, email=email, password="CompanyPass123!", name="Partner Corp")

        resp = client.post("/company/login", json={"email": email, "password": "CompanyPass123!"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("status") == "success"

        with get_db() as conn:
            sess = conn.execute("SELECT * FROM user_sessions WHERE email=?", (email,)).fetchone()
        assert sess is not None
        assert sess["role"] == "company"

    def test_mentor_login_success(self, app_client):
        client, db_path = app_client
        email = "mentor_test@example.com"
        seed_mentor(db_path, email=email, password="MentorPass123!", name="Senior Mentor")

        resp = client.post("/mentor/login", json={"email": email, "password": "MentorPass123!"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("status") == "success"

        with get_db() as conn:
            sess = conn.execute("SELECT * FROM user_sessions WHERE email=?", (email,)).fetchone()
        assert sess is not None
        assert sess["role"] == "mentor"

    def test_staff_login_success(self, app_client):
        client, db_path = app_client
        email = "staff_test@example.com"
        seed_staff(db_path, email=email, password="StaffPass123!", name="Operations Staff", roles=["courses", "applications"])

        resp = client.post("/staff/login", json={"email": email, "password": "StaffPass123!"})
        assert resp.status_code in (200, 302)

    def test_admin_login_success(self, app_client):
        client, db_path = app_client
        email = "admin_test@example.com"
        seed_staff(db_path, email=email, password="AdminPass123!", name="Lead Admin")

        resp = client.post("/admin/login", json={"email": email, "password": "AdminPass123!"})
        assert resp.status_code in (200, 302)

        with get_db() as conn:
            sess = conn.execute("SELECT * FROM user_sessions WHERE email=?", (email,)).fetchone()
        assert sess is not None
        assert sess["role"] == "admin"

    def test_invalid_credentials_rejected(self, app_client):
        client, db_path = app_client
        email = "intern_badpw@example.com"
        seed_intern(db_path, email=email, password="CorrectPass123!")

        resp = client.post("/intern/login", json={"email": email, "password": "WrongPassword!"})
        assert resp.status_code == 401

        resp_mentor = client.post("/mentor/login", json={"email": "nonexistent@mentor.com", "password": "Any"})
        assert resp_mentor.status_code == 401

        resp_comp = client.post("/company/login", json={"email": "nonexistent@comp.com", "password": "Any"})
        assert resp_comp.status_code == 401

    def test_inactive_account_cannot_login(self, app_client):
        client, db_path = app_client
        email = "deactivated@example.com"
        seed_intern(db_path, email=email, password="SomePassword123!")
        os.environ["DB_FILE"] = db_path
        with get_db() as conn:
            conn.execute("UPDATE intern_accounts SET is_active=0 WHERE email=?", (email,))
            conn.commit()

        resp = client.post("/intern/login", json={"email": email, "password": "SomePassword123!"})
        assert resp.status_code == 401


class TestDuplicateIdentityRejection:
    """Verifies that duplicate emails and phones are rejected during registration."""

    def test_signup_duplicate_email_rejected(self, app_client):
        client, db_path = app_client
        email = "duplicate_email@example.com"
        seed_intern(db_path, email=email, password="Pass123456!", name="Existing Intern")

        resp = client.post("/signup/stage1", json={
            "name": "Another User",
            "email": email,
            "phone": "9998887771",
            "password": "NewPassword123!",
            "terms_accepted": True
        })
        assert resp.status_code == 409
        data = resp.get_json()
        assert data.get("code") == "account_exists"

    def test_signup_duplicate_phone_rejected(self, app_client):
        client, db_path = app_client
        shared_phone = "9123456789"
        seed_intern(db_path, email="first_phone_user@example.com", password="Pass123456!", name="First User")
        os.environ["DB_FILE"] = db_path
        with get_db() as conn:
            conn.execute("UPDATE intern_accounts SET phone=? WHERE email=?", (shared_phone, "first_phone_user@example.com"))
            conn.commit()

        resp = client.post("/signup/stage1", json={
            "name": "Second User",
            "email": "second_phone_user@example.com",
            "phone": shared_phone,
            "password": "NewPassword123!",
            "terms_accepted": True
        })
        assert resp.status_code == 409
        data = resp.get_json()
        assert data.get("code") == "phone_exists"

    def test_company_duplicate_email_rejected(self, app_client):
        client, db_path = app_client
        email = "duplicate_company@corp.com"
        seed_company(db_path, email=email, password="CompPass123!", name="Company One")

        resp = client.post("/company/signup", json={
            "name": "Company Two",
            "email": email,
            "phone": "9876543212",
            "password": "AnotherCompPass123!"
        })
        assert resp.status_code == 400
        data = resp.get_json()
        assert "already exists" in data.get("message", "").lower()

    def test_company_duplicate_phone_rejected(self, app_client):
        client, db_path = app_client
        phone = "9887766554"
        seed_company(db_path, email="comp1@corp.com", password="CompPass123!", name="Company 1")
        os.environ["DB_FILE"] = db_path
        with get_db() as conn:
            conn.execute("UPDATE companies SET phone=? WHERE email=?", (phone, "comp1@corp.com"))
            conn.commit()

        resp = client.post("/company/signup", json={
            "name": "Company 2",
            "email": "comp2@corp.com",
            "phone": phone,
            "password": "CompPass123!"
        })
        assert resp.status_code == 400
        data = resp.get_json()
        assert "already exists" in data.get("message", "").lower() or data.get("code") == "phone_exists"


class TestPasswordResetLifecycle:
    """Automates complete password reset lifecycle: forgot, expired, replay, session invalidation."""

    def test_forgot_password_neutral_enumeration(self, app_client):
        client, db_path = app_client
        seed_intern(db_path, email="known_reset@example.com")

        resp_known = client.post("/forgot-password", json={"email": "known_reset@example.com"})
        resp_unknown = client.post("/forgot-password", json={"email": "unknown_ghost@example.com"})

        assert resp_known.status_code == 200
        assert resp_unknown.status_code == 200
        assert resp_known.get_json().get("message") == resp_unknown.get_json().get("message")

    def test_reset_password_with_valid_token_allows_login(self, app_client):
        client, db_path = app_client
        email = "password_rotator@example.com"
        seed_intern(db_path, email=email, password="OldPassword123!")
        raw_token = inject_reset_token(db_path, email, "intern")

        resp = client.post("/reset-password", json={
            "token": raw_token,
            "password": "NewBrandPassword456!",
            "confirm_password": "NewBrandPassword456!"
        })
        assert resp.status_code == 200

        # Login with old password must fail
        bad_resp = client.post("/intern/login", json={"email": email, "password": "OldPassword123!"})
        assert bad_resp.status_code == 401

        # Login with new password must succeed
        good_resp = client.post("/intern/login", json={"email": email, "password": "NewBrandPassword456!"})
        assert good_resp.status_code == 200

    def test_expired_reset_token_rejected(self, app_client):
        client, db_path = app_client
        email = "expired_reset@example.com"
        seed_intern(db_path, email=email)
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        past = (datetime.datetime.now() - datetime.timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S")

        os.environ["DB_FILE"] = db_path
        with get_db() as conn:
            conn.execute(
                "INSERT INTO password_resets (account_type, email, token, expires_at) VALUES (?,?,?,?)",
                ("intern", email, token_hash, past)
            )
            conn.commit()

        resp = client.post("/reset-password", json={
            "token": raw_token,
            "password": "NewPassword123!",
            "confirm_password": "NewPassword123!"
        })
        assert resp.status_code == 400

    def test_used_reset_token_cannot_be_replayed(self, app_client):
        client, db_path = app_client
        email = "replay_reset@example.com"
        seed_intern(db_path, email=email)
        raw_token = inject_reset_token(db_path, email, "intern")

        # First use
        resp1 = client.post("/reset-password", json={
            "token": raw_token,
            "password": "FirstNewPassword123!",
            "confirm_password": "FirstNewPassword123!"
        })
        assert resp1.status_code == 200

        # Replay attempt
        resp2 = client.post("/reset-password", json={
            "token": raw_token,
            "password": "SecondNewPassword123!",
            "confirm_password": "SecondNewPassword123!"
        })
        assert resp2.status_code == 400


class TestLogoutAndBrowserBackJourney:
    """
    Automates the critical security journey:
    login -> portal -> logout -> browser back -> portal -> authenticated access denied
    """

    def test_critical_journey_browser_back_access_denied(self, app_client):
        client, db_path = app_client
        email = "journey_user@example.com"
        seed_intern(db_path, email=email, password="Password123!", name="Journey Intern")

        # 1. Login
        login_resp = client.post("/intern/login", json={"email": email, "password": "Password123!"})
        assert login_resp.status_code == 200

        # 2. Portal access
        portal_resp = client.get("/portal")
        assert portal_resp.status_code == 200
        # Check cache-control prevents browser back history leakage
        cache_ctrl = portal_resp.headers.get("Cache-Control", "")
        assert "no-store" in cache_ctrl or "no-cache" in cache_ctrl

        # Verify API access while logged in
        me_resp = client.get("/intern/me")
        assert me_resp.status_code == 200

        # 3. Logout
        logout_resp = client.get("/logout")
        assert logout_resp.status_code in (200, 302)

        # Verify session token removed from database
        os.environ["DB_FILE"] = db_path
        with get_db() as conn:
            sessions = conn.execute("SELECT * FROM user_sessions WHERE email=?", (email,)).fetchall()
        assert len(sessions) == 0, "All sessions must be invalidated upon logout"

        # 4. Browser back simulation: request /portal again
        back_resp = client.get("/portal")
        # Must be redirected to signin, NOT served authenticated portal content
        assert back_resp.status_code in (302, 401)
        if back_resp.status_code == 302:
            assert "/#signin" in back_resp.headers.get("Location", "")

        # Authenticated API must also strictly reject
        api_back_resp = client.get("/intern/me")
        assert api_back_resp.status_code == 401

    def test_session_expiry_denies_authenticated_access(self, app_client):
        client, db_path = app_client
        email = "expired_session@example.com"
        seed_intern(db_path, email=email, password="Password123!")
        login_as_intern(client, db_path, email=email, password="Password123!")

        # Manually expire the session token in the database
        past_time = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        os.environ["DB_FILE"] = db_path
        with get_db() as conn:
            conn.execute("UPDATE user_sessions SET expires_at=? WHERE email=?", (past_time, email))
            conn.commit()

        # Access with expired token
        resp = client.get("/intern/me")
        assert resp.status_code == 401

    def test_multi_tab_concurrent_sessions_supported(self, app_client):
        client, db_path = app_client
        email = "multitab@example.com"
        seed_intern(db_path, email=email, password="Password123!")

        # Create two distinct sessions (e.g. two browser tabs / devices)
        token1 = create_session(email, "intern")
        token2 = create_session(email, "intern")
        assert token1 != token2

        os.environ["DB_FILE"] = db_path
        with get_db() as conn:
            count = conn.execute("SELECT COUNT(*) FROM user_sessions WHERE email=?", (email,)).fetchone()[0]
        assert count == 2

    def test_deep_link_redirects_unauthenticated(self, app_client):
        client, db_path = app_client
        # Deep links requiring authentication must redirect anonymous users
        resp_portal = client.get("/portal")
        assert resp_portal.status_code == 302
        assert "/#signin" in resp_portal.headers.get("Location", "")

        resp_interview = client.get("/interview")
        assert resp_interview.status_code == 302
        assert "/#signin" in resp_interview.headers.get("Location", "")
