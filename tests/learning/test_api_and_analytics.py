"""
Tests for Guided Learning 2.0 API Endpoints, Mentor Analytics Dashboard, and Feature Flag.
Covers:
- POST /api/learning/v2/session
- POST /api/learning/v2/turn
- GET /api/learning/v2/reviews-due
- GET /api/learning/v2/concept-tree/<course_id>
- GET /admin/learning-analytics (Auth guard, HTML template, JSON format)
- Feature flag GUIDED_LEARNING_V2 toggling and backwards compatibility
"""
import pytest
import json
import os
from app import create_session, AUTH_COOKIE, set_password_hash
from services.learning.learning_models import Concept, init_learning_tables
from services.learning.concept_service import ConceptService
from tests.conftest import seed_intern

@pytest.fixture
def api_test_env(app_client):
    """Sets up enrolled intern and admin users with session auth."""
    client, db_path = app_client
    intern_email = "api_intern@dbert.test"
    admin_email = "api_admin@dbert.test"
    csrf_token = "test_csrf_token_api_123"

    intern_id = seed_intern(db_path, email=intern_email, password="Password123", status="Accepted")

    with client.application.app_context():
        from app import get_db
        with get_db() as conn:
            init_learning_tables(conn)
            # Create admin account
            conn.execute(
                "INSERT OR REPLACE INTO staff_accounts (name, email, password_hash, is_active) VALUES ('Admin', ?, ?, 1)",
                (admin_email, set_password_hash("AdminPass123"))
            )
            # Check or create course & concept
            course = conn.execute("SELECT id FROM courses LIMIT 1").fetchone()
            if not course:
                conn.execute(
                    "INSERT INTO courses (title, slug, domain, is_active) VALUES ('Python AI', 'python-ai', 'AI Agent Development', 1)"
                )
                course_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            else:
                course_id = course["id"]

            c = Concept(
                concept_id="api.py.test",
                name="API Testing Concept",
                description="Testing Concept Description",
                domain="AI Agent Development",
                subject="API Testing",
                difficulty=1,
                learning_objectives=["Understand API testing"],
                assessment_criteria=["Valid assertions"]
            )
            ConceptService.register_concept(conn, c)

            # Enroll intern
            conn.execute(
                "INSERT OR IGNORE INTO course_enrollments (intern_id, course_id, email, current_day) VALUES (?, ?, ?, 1)",
                (intern_id, course_id, intern_email)
            )
            conn.commit()

    return {
        "client": client,
        "intern_id": intern_id,
        "intern_email": intern_email,
        "admin_email": admin_email,
        "course_id": course_id,
        "csrf_token": csrf_token
    }


def login_as(client, email, role, csrf_token):
    token = create_session(email, role=role)
    client.set_cookie(AUTH_COOKIE, token)
    with client.session_transaction() as sess:
        sess["_csrf"] = csrf_token
    return token


class TestGuidedLearningAPIAndAnalytics:
    """Verifies REST endpoints and admin learning analytics dashboard."""

    def test_api_session_lifecycle(self, api_test_env):
        client = api_test_env["client"]
        email = api_test_env["intern_email"]
        course_id = api_test_env["course_id"]
        csrf = api_test_env["csrf_token"]
        login_as(client, email, "intern", csrf)

        # Unenrolled course returns 403
        res_unenrolled = client.post(
            "/api/learning/v2/session",
            json={"course_id": 99999},
            headers={"X-CSRF-Token": csrf}
        )
        assert res_unenrolled.status_code == 403

        # Valid enrolled course returns 200 with session and concept
        res = client.post(
            "/api/learning/v2/session",
            json={"course_id": course_id},
            headers={"X-CSRF-Token": csrf}
        )
        assert res.status_code == 200
        data = res.get_json()["data"]
        assert "session" in data
        assert data["session"]["session_id"].startswith("gl_sess_")
        assert "concept" in data

    def test_api_turn_execution(self, api_test_env):
        client = api_test_env["client"]
        email = api_test_env["intern_email"]
        course_id = api_test_env["course_id"]
        csrf = api_test_env["csrf_token"]
        login_as(client, email, "intern", csrf)

        # 1. Initialize session
        sess_res = client.post(
            "/api/learning/v2/session",
            json={"course_id": course_id},
            headers={"X-CSRF-Token": csrf}
        )
        session_id = sess_res.get_json()["data"]["session"]["session_id"]

        # 2. Submit turn
        turn_res = client.post(
            "/api/learning/v2/turn",
            json={
                "session_id": session_id,
                "message": "Valid assertions demonstrate understanding of API criteria.",
                "idempotency_key": "api_turn_1"
            },
            headers={"X-CSRF-Token": csrf}
        )
        assert turn_res.status_code == 200
        data = turn_res.get_json()["data"]
        assert "evaluation" in data
        assert "mastery" in data
        assert "recommendation" in data
        assert data["mastery"]["total_attempts"] == 1

    def test_api_reviews_due(self, api_test_env):
        client = api_test_env["client"]
        email = api_test_env["intern_email"]
        csrf = api_test_env["csrf_token"]
        login_as(client, email, "intern", csrf)

        res = client.get("/api/learning/v2/reviews-due")
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "success"
        assert "reviews" in data

    def test_api_concept_tree(self, api_test_env):
        client = api_test_env["client"]
        email = api_test_env["intern_email"]
        course_id = api_test_env["course_id"]
        csrf = api_test_env["csrf_token"]
        login_as(client, email, "intern", csrf)

        res = client.get(f"/api/learning/v2/concept-tree/{course_id}")
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "success"
        assert "concepts" in data
        assert len(data["concepts"]) >= 1

    def test_admin_learning_analytics_access_control(self, api_test_env):
        client = api_test_env["client"]
        csrf = api_test_env["csrf_token"]

        # 1. Unauthenticated redirects to admin login
        res_anon = client.get("/admin/learning-analytics")
        assert res_anon.status_code in (302, 401)

        # 2. Intern role blocked
        login_as(client, api_test_env["intern_email"], "intern", csrf)
        res_intern = client.get("/admin/learning-analytics")
        assert res_intern.status_code in (302, 403)

        # 3. Admin role renders dashboard successfully
        login_as(client, api_test_env["admin_email"], "admin", csrf)
        res_admin = client.get("/admin/learning-analytics")
        assert res_admin.status_code == 200
        assert b"Guided Learning" in res_admin.data

        # 4. Admin JSON request returns structured analytics
        res_json = client.get("/admin/learning-analytics?format=json")
        assert res_json.status_code == 200
        analytics = res_json.get_json()["analytics"]
        assert "total_learners" in analytics
        assert "mastered_count" in analytics
        assert "escalations" in analytics
        assert "domains" in analytics

    def test_feature_flag_fallback(self, api_test_env, monkeypatch):
        """Verifies is_guided_learning_v2_enabled correctly checks environment."""
        from app import is_guided_learning_v2_enabled

        # Default is false
        monkeypatch.setenv("GUIDED_LEARNING_V2", "false")
        assert is_guided_learning_v2_enabled() is False

        # Explicitly enabled
        monkeypatch.setenv("GUIDED_LEARNING_V2", "true")
        assert is_guided_learning_v2_enabled() is True
