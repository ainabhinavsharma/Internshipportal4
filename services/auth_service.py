"""
services/auth_service.py - Central Authentication & Session Domain Service
Fulfills Phase 23 (Monolith Modularization) of INTERNSHIPPORTAL4_LOCAL_AI_AGENT_MASTER_PLAN.md

Encapsulates:
1. Salted password hashing (Werkzeug PBKDF2:SHA256) & constant-time legacy migration.
2. Database-backed session tokens (user_sessions) with opportunistic expiry cleanup.
3. Multi-role authorization checks (intern, company, mentor, staff, admin).
"""
import os
import re
import hmac
import time
import secrets
import hashlib
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from flask import request, session

SESSION_DAYS = int(os.environ.get("SESSION_DAYS", "30"))
AUTH_COOKIE = "dbert_auth"
LEGACY_AUTH_COOKIE = "dbert_session"

_LEGACY_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


class AuthService:
    """Authentication and session management domain service."""

    @staticmethod
    def is_legacy_hash(stored_hash: str) -> bool:
        """True only for the old bare unsalted SHA-256 (64 lowercase hex) format."""
        return bool(stored_hash) and bool(_LEGACY_HASH_RE.match(stored_hash))

    @staticmethod
    def hash_password(plaintext: str) -> str:
        """Legacy bare SHA-256 hash calculation."""
        return hashlib.sha256((plaintext or "").encode()).hexdigest()

    @staticmethod
    def set_password_hash(plaintext: str) -> str:
        """Hash a password for storage with salted KDF (pbkdf2:sha256)."""
        if os.environ.get("TESTING") == "true":
            return generate_password_hash(plaintext or "", method="pbkdf2:sha256:1000")
        return generate_password_hash(plaintext or "", method="pbkdf2:sha256")

    @staticmethod
    def verify_password(stored_hash: str, plaintext: str) -> bool:
        """Constant-time verify against either legacy SHA-256 or salted KDF hash."""
        if not stored_hash:
            return False
        if AuthService.is_legacy_hash(stored_hash):
            return hmac.compare_digest(stored_hash, AuthService.hash_password(plaintext))
        try:
            return check_password_hash(stored_hash, plaintext or "")
        except Exception:
            return False

    @staticmethod
    def migrate_password_hash(conn, table: str, email: str, plaintext: str) -> bool:
        """Lazy migration: re-hash a verified legacy password to salted KDF."""
        if table not in ("intern_accounts", "mentors", "companies", "staff_accounts"):
            return False
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                f"UPDATE {table} SET password_hash=?, updated_at=? WHERE email=?",  # nosec B608
                (AuthService.set_password_hash(plaintext), now, email.lower()),
            )
            conn.commit()
            return True
        except Exception:
            return False

    @staticmethod
    def create_session(conn, email: str, role: str) -> str:
        """Generates a secure 32-byte token and inserts an active session."""
        token = secrets.token_hex(32)
        expires_at = (datetime.now() + timedelta(days=SESSION_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "INSERT INTO user_sessions (email, role, session_token, expires_at) VALUES (?, ?, ?, ?)",
            (email.lower(), role, token, expires_at)
        )
        conn.commit()
        return token

    @staticmethod
    def invalidate_session(conn, token: str) -> bool:
        """Revokes a session by deleting it from user_sessions."""
        if not token:
            return False
        conn.execute("DELETE FROM user_sessions WHERE session_token=?", (token,))
        conn.commit()
        return True

    @staticmethod
    def get_session_token_from_request() -> str:
        """Extracts auth token from cookies or X-Session-Token header."""
        return (request.cookies.get(AUTH_COOKIE)
                or request.cookies.get(LEGACY_AUTH_COOKIE)
                or request.headers.get("X-Session-Token")
                or "")

    @staticmethod
    def get_current_user(conn) -> dict:
        """Resolves active user session dict or None."""
        token = AuthService.get_session_token_from_request()
        if not token:
            return None
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row = conn.execute(
            "SELECT * FROM user_sessions WHERE session_token=? AND expires_at>?",
            (token, now)
        ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def require_role(conn, role):
        """Enforces matching user role (str, list, tuple, or set)."""
        user = AuthService.get_current_user(conn)
        if not user:
            return None
        user_role = user.get("role")
        if isinstance(role, (list, tuple, set)):
            if user_role not in role:
                return None
        elif user_role != role:
            return None
        return user

    @staticmethod
    def current_intern(conn) -> dict:
        """Returns the logged-in intern_accounts row or None."""
        user = AuthService.require_role(conn, "intern")
        if not user:
            return None
        row = conn.execute(
            "SELECT * FROM intern_accounts WHERE LOWER(email)=LOWER(?) AND is_active=1 LIMIT 1",
            (user["email"],)
        ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def current_company(conn) -> dict:
        """Returns the logged-in companies row or None."""
        user = AuthService.require_role(conn, "company")
        if not user:
            return None
        row = conn.execute(
            "SELECT * FROM companies WHERE LOWER(email)=LOWER(?) AND is_active=1 LIMIT 1",
            (user["email"],)
        ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def current_mentor(conn) -> dict:
        """Returns the logged-in mentors row or None."""
        user = AuthService.require_role(conn, "mentor")
        if not user:
            return None
        row = conn.execute(
            "SELECT * FROM mentors WHERE LOWER(email)=LOWER(?) AND is_active=1 LIMIT 1",
            (user["email"],)
        ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def current_staff(conn) -> dict:
        """Returns the logged-in staff_accounts row or None."""
        staff_id = session.get("staff_id")
        if not staff_id:
            return None
        row = conn.execute(
            "SELECT * FROM staff_accounts WHERE id=? AND is_active=1 LIMIT 1",
            (staff_id,)
        ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def require_admin(conn) -> dict:
        """Admin check for session-based admin authentication."""
        user = AuthService.get_current_user(conn)
        if user and user.get("role") in ("admin", "superadmin"):
            return user
        if session.get("admin_id"):
            return {
                "id": session.get("admin_id"),
                "role": session.get("role") or "admin",
                "email": session.get("staff_email", "admin@dbert.online")
            }
        if session.get("role") in ("admin", "superadmin"):
            return {
                "id": session.get("admin_id", 1),
                "role": session.get("role"),
                "email": session.get("staff_email", "admin@dbert.online")
            }
        return None
