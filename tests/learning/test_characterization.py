"""
Characterization tests for Guided Learning baseline (V1).
Captures existing behavior to ensure zero regressions during V2 development.
"""
import pytest
import json
from app import create_session, AUTH_COOKIE
from tests.conftest import seed_intern

@pytest.fixture
def enrolled_intern_client(app_client):
    """Creates an accepted and enrolled intern with active session."""
    client, db_path = app_client
    intern_email = "characterization_intern@example.com"
    csrf_token = "test_csrf_token_12345"
    intern_id = seed_intern(db_path, email=intern_email, password="Password123", status="Accepted")
    
    with client.application.app_context():
        from app import get_db
        with get_db() as conn:
            # Check or create course and subtopic
            course = conn.execute("SELECT id FROM courses LIMIT 1").fetchone()
            if not course:
                conn.execute(
                    "INSERT INTO courses (title, slug, domain, is_active) VALUES ('Python Foundations', 'python-foundations', 'AI Agent Development', 1)"
                )
                course_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                conn.execute("INSERT INTO course_chapters (course_id, day_number, title) VALUES (?, 1, 'Intro')", (course_id,))
                chapter_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                conn.execute(
                    "INSERT INTO course_subtopics (chapter_id, sort_order, title, brief, key_takeaways_json) "
                    "VALUES (?, 1, 'Variables', 'Learn variables', '[\"variables\", \"assignments\"]')",
                    (chapter_id,)
                )
            else:
                course_id = course["id"]
                # Ensure chapter and subtopic exist for this course
                chap = conn.execute("SELECT id FROM course_chapters WHERE course_id = ?", (course_id,)).fetchone()
                if not chap:
                    conn.execute("INSERT INTO course_chapters (course_id, day_number, title) VALUES (?, 1, 'Intro')", (course_id,))
                    chap_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                else:
                    chap_id = chap["id"]
                sub = conn.execute("SELECT id FROM course_subtopics WHERE chapter_id = ?", (chap_id,)).fetchone()
                if not sub:
                    conn.execute(
                        "INSERT INTO course_subtopics (chapter_id, sort_order, title, brief, key_takeaways_json) "
                        "VALUES (?, 1, 'Variables', 'Learn variables', '[\"variables\"]')",
                        (chap_id,)
                    )
                
            # Enroll the intern
            conn.execute(
                "INSERT OR REPLACE INTO course_enrollments (intern_id, course_id, email, current_day) VALUES (?, ?, ?, 1)",
                (intern_id, course_id, intern_email)
            )
            conn.commit()

        # Log in via session cookie
        token = create_session(intern_email, role="intern")
        client.set_cookie(AUTH_COOKIE, token)
        with client.session_transaction() as sess:
            sess["_csrf"] = csrf_token
    
    return {
        "client": client,
        "db_path": db_path,
        "intern_id": intern_id,
        "email": intern_email,
        "course_id": course_id,
        "csrf_token": csrf_token
    }


class TestGuidedLearningCharacterization:
    """Verifies baseline endpoints for existing Guided Learning."""

    def test_learn_page_unauthenticated_redirects(self, app_client):
        client, _ = app_client
        res = client.get("/courses/1/learn")
        assert res.status_code in (302, 401)
        assert "/#signin" in res.headers.get("Location", "") or res.status_code == 401

    def test_learn_page_enrolled_renders_200(self, enrolled_intern_client):
        client = enrolled_intern_client["client"]
        course_id = enrolled_intern_client["course_id"]
        res = client.get(f"/courses/{course_id}/learn")
        assert res.status_code == 200
        assert b"course" in res.data.lower() or b"chapter" in res.data.lower()

    def test_learn_page_unenrolled_redirects(self, enrolled_intern_client):
        client = enrolled_intern_client["client"]
        res = client.get("/courses/99999/learn")
        assert res.status_code in (302, 404)

    def test_chat_without_csrf_returns_403(self, app_client):
        client, _ = app_client
        res = client.post("/courses/1/subtopic/1/chat", json={"message": "hello"})
        assert res.status_code == 403

    def test_chat_unauthenticated_with_csrf_returns_401(self, app_client):
        client, _ = app_client
        csrf_token = "test_csrf_anon_123"
        with client.session_transaction() as sess:
            sess["_csrf"] = csrf_token
        res = client.post(
            "/courses/1/subtopic/1/chat",
            json={"message": "hello"},
            headers={"X-CSRF-Token": csrf_token}
        )
        assert res.status_code == 401

    def test_chat_empty_message_returns_400(self, enrolled_intern_client):
        client = enrolled_intern_client["client"]
        course_id = enrolled_intern_client["course_id"]
        csrf_token = enrolled_intern_client["csrf_token"]
        res = client.post(
            f"/courses/{course_id}/subtopic/1/chat",
            json={"message": "   "},
            headers={"X-CSRF-Token": csrf_token}
        )
        assert res.status_code == 400
        data = res.get_json()
        assert data["status"] == "error"

    def test_chat_accidental_autofill_returns_400(self, enrolled_intern_client):
        client = enrolled_intern_client["client"]
        course_id = enrolled_intern_client["course_id"]
        csrf_token = enrolled_intern_client["csrf_token"]
        res = client.post(
            f"/courses/{course_id}/subtopic/1/chat",
            json={"message": "user@example.com"},
            headers={"X-CSRF-Token": csrf_token}
        )
        assert res.status_code == 400
        data = res.get_json()
        assert "enter a question" in data["message"].lower()

    def test_chat_nonexistent_subtopic_returns_404(self, enrolled_intern_client):
        client = enrolled_intern_client["client"]
        course_id = enrolled_intern_client["course_id"]
        csrf_token = enrolled_intern_client["csrf_token"]
        res = client.post(
            f"/courses/{course_id}/subtopic/999999/chat",
            json={"message": "What is Python?"},
            headers={"X-CSRF-Token": csrf_token}
        )
        assert res.status_code == 404

    def test_intern_tutor_progress_endpoint(self, enrolled_intern_client):
        client = enrolled_intern_client["client"]
        res = client.get("/intern/tutor-progress")
        assert res.status_code == 200
        data = res.get_json()
        assert "all_courses" in data or "overall_completion_pct" in data or "courses" in data
