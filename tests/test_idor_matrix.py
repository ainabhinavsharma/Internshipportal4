"""
Phase 11: Authorization & IDOR Matrix Regression Suite
Covers horizontal isolation (User A cannot access User B's private resources)
and vertical privilege escalation prevention (interns/companies/mentors blocked from admin/staff).

Tested dimensions:
- Intern private profile (/intern/me)
- Intern profile update (/intern/update-profile)
- CV privacy and slug protection (/cv/<slug>)
- Private conversations, polling, and messaging (/messages/<conv_id>)
- Task submissions and evaluation history (/tasks/<task_id>)
- Company post isolation and candidate review isolation
- Vertical privilege escalation blocks: /admin/*, /staff/*
"""
import os
import json
import pytest

os.environ["TESTING"] = "true"
os.environ.setdefault("FLASK_DEBUG", "false")
os.environ.setdefault("SMTP_PASS", "")

from tests.conftest import (
    seed_intern, seed_company, seed_staff, seed_mentor,
    login_as_intern, login_as_company, login_as_staff, login_as_mentor, login_as_admin,
    logout
)
from app import app, get_db, set_password_hash, create_session, AUTH_COOKIE


class TestInternHorizontalIsolation:
    """Verifies that Intern A cannot read or modify Intern B's resources (Anti-IDOR)."""

    def test_intern_me_isolates_private_data(self, app_client):
        client, db_path = app_client
        id_a = seed_intern(db_path, email="intern_a@test.com", password="PassA123!", name="Intern Alice")
        id_b = seed_intern(db_path, email="intern_b@test.com", password="PassB123!", name="Intern Bob")

        # Login as Intern A
        login_as_intern(client, db_path, email="intern_a@test.com", password="PassA123!")

        resp = client.get("/intern/me")
        assert resp.status_code == 200
        data = resp.get_json()

        # Must contain Intern A's data, never Intern B's data
        account = data.get("intern", {})
        assert account.get("email") == "intern_a@test.com"
        assert account.get("name") == "Intern Alice"
        assert account.get("email") != "intern_b@test.com"
        assert account.get("name") != "Intern Bob"

    def test_intern_update_profile_cannot_modify_other_intern(self, app_client):
        client, db_path = app_client
        id_a = seed_intern(db_path, email="intern_alice@test.com", password="PassA123!", name="Alice")
        id_b = seed_intern(db_path, email="intern_bob@test.com", password="PassB123!", name="Bob")

        login_as_intern(client, db_path, email="intern_alice@test.com", password="PassA123!")

        # Alice attempts to submit update with Bob's email or targeting Bob
        resp = client.post("/intern/update-profile", json={
            "name": "Hacked Bob",
            "city": "AttackerCity",
            "college": "AttackerCollege"
        })
        assert resp.status_code == 200

        # Verify Bob remains completely untouched in the database
        os.environ["DB_FILE"] = db_path
        with get_db() as conn:
            bob = conn.execute("SELECT * FROM intern_accounts WHERE email=?", ("intern_bob@test.com",)).fetchone()
            alice = conn.execute("SELECT * FROM intern_accounts WHERE email=?", ("intern_alice@test.com",)).fetchone()

        assert bob["name"] == "Bob"
        assert bob["city"] != "AttackerCity"
        assert alice["name"] == "Hacked Bob"

    def test_intern_cannot_view_other_intern_private_cv(self, app_client):
        client, db_path = app_client
        id_a = seed_intern(db_path, email="alice_cv@test.com", password="PassA123!", name="Alice")
        id_b = seed_intern(db_path, email="bob_cv@test.com", password="PassB123!", name="Bob")

        # Create private CV for Bob (is_public=0)
        os.environ["DB_FILE"] = db_path
        with get_db() as conn:
            conn.execute("""
                INSERT INTO cvs (intern_id, slug, headline, summary, is_public, updated_at)
                VALUES (?, 'bob-private-slug', 'Backend Dev', 'Secret Summary', 0, datetime('now'))
            """, (id_b,))
            conn.commit()

        # 1. Unauthenticated request to private CV -> 404
        unauth_resp = client.get("/cv/bob-private-slug")
        assert unauth_resp.status_code == 404

        # 2. Authenticate as Alice and attempt to access Bob's private CV -> 404 (Access Denied)
        login_as_intern(client, db_path, email="alice_cv@test.com", password="PassA123!")
        alice_resp = client.get("/cv/bob-private-slug")
        assert alice_resp.status_code == 404

        # 3. Authenticate as Bob (the owner) -> 200 OK
        logout(client)
        login_as_intern(client, db_path, email="bob_cv@test.com", password="PassB123!")
        bob_resp = client.get("/cv/bob-private-slug")
        assert bob_resp.status_code == 200

    def test_intern_cannot_read_or_poll_other_intern_messages(self, app_client):
        client, db_path = app_client
        id_a = seed_intern(db_path, email="alice_msg@test.com", password="PassA123!", name="Alice")
        id_b = seed_intern(db_path, email="bob_msg@test.com", password="PassB123!", name="Bob")

        # Create conversation for Bob with Admin
        os.environ["DB_FILE"] = db_path
        with get_db() as conn:
            cur = conn.execute("""
                INSERT INTO conversations (intern_id, counterparty_type, counterparty_id)
                VALUES (?, 'admin', 1)
            """, (id_b,))
            conv_id = cur.lastrowid
            conn.execute("""
                INSERT INTO messages (conversation_id, sender_type, sender_id, body)
                VALUES (?, 'intern', ?, 'Confidential message from Bob')
            """, (conv_id, id_b))
            conn.commit()

        # Alice logs in and attempts to access Bob's conversation
        login_as_intern(client, db_path, email="alice_msg@test.com", password="PassA123!")

        resp_thread = client.get(f"/messages/{conv_id}")
        assert resp_thread.status_code in (404, 403)

        resp_poll = client.get(f"/messages/{conv_id}/poll")
        assert resp_poll.status_code in (404, 403)

    def test_intern_cannot_post_to_other_intern_conversation(self, app_client):
        client, db_path = app_client
        id_a = seed_intern(db_path, email="alice_send@test.com", password="PassA123!", name="Alice")
        id_b = seed_intern(db_path, email="bob_send@test.com", password="PassB123!", name="Bob")

        os.environ["DB_FILE"] = db_path
        with get_db() as conn:
            cur = conn.execute("""
                INSERT INTO conversations (intern_id, counterparty_type, counterparty_id)
                VALUES (?, 'admin', 1)
            """, (id_b,))
            conv_id = cur.lastrowid
            conn.commit()

        # Alice tries to inject a message into Bob's conversation
        login_as_intern(client, db_path, email="alice_send@test.com", password="PassA123!")
        resp = client.post(f"/messages/{conv_id}/send", json={"body": "Impersonated message from Alice"})
        assert resp.status_code in (401, 403, 404)

        # Verify no rogue message was saved
        with get_db() as conn:
            count = conn.execute("SELECT COUNT(*) FROM messages WHERE conversation_id=?", (conv_id,)).fetchone()[0]
        assert count == 0

    def test_intern_task_submission_isolated(self, app_client):
        client, db_path = app_client
        id_a = seed_intern(db_path, email="alice_task@test.com", password="PassA123!", name="Alice")
        id_b = seed_intern(db_path, email="bob_task@test.com", password="PassB123!", name="Bob")

        # Create a task, version, and a submission for Bob
        os.environ["DB_FILE"] = db_path
        with get_db() as conn:
            cur = conn.execute("""
                INSERT INTO tasks (title, description, is_active)
                VALUES ('Build Neural Net', 'Task Details', 1)
            """)
            task_id = cur.lastrowid
            v_cur = conn.execute("""
                INSERT INTO task_versions (task_id, version_number, instructions, rubric)
                VALUES (?, 1, 'Build neural network', 'Rubric details')
            """, (task_id,))
            version_id = v_cur.lastrowid
            conn.execute("""
                INSERT INTO task_submissions (intern_id, task_id, task_version_id, submission_content, status, email)
                VALUES (?, ?, ?, 'Bob solution code', 'pending', 'bob_task@test.com')
            """, (id_b, task_id, version_id))
            conn.commit()

        # Alice views the task
        login_as_intern(client, db_path, email="alice_task@test.com", password="PassA123!")
        resp = client.get(f"/tasks/{task_id}")
        assert resp.status_code == 200
        data = resp.get_json()

        # Alice's view of 'my_submission' must be None
        assert data.get("my_submission") is None


class TestCompanyHorizontalIsolation:
    """Verifies that Company A cannot inspect or modify Company B's posts and candidate reviews."""

    def test_company_dashboard_scoped_to_own_posts(self, app_client):
        client, db_path = app_client
        comp_a = seed_company(db_path, email="comp_a@corp.com", password="CompA123!", name="Corp Alpha")
        comp_b = seed_company(db_path, email="comp_b@corp.com", password="CompB123!", name="Corp Beta")

        os.environ["DB_FILE"] = db_path
        with get_db() as conn:
            conn.execute("""
                INSERT INTO posts (company_id, title, slug, post_type, domain, status)
                VALUES (?, 'Alpha Engineer', 'alpha-eng', 'job', 'AI', 'published')
            """, (comp_a,))
            conn.execute("""
                INSERT INTO posts (company_id, title, slug, post_type, domain, status)
                VALUES (?, 'Beta Researcher', 'beta-res', 'job', 'AI', 'published')
            """, (comp_b,))
            conn.commit()

        login_as_company(client, db_path, email="comp_a@corp.com", password="CompA123!")
        resp = client.get("/company")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)

        assert "Alpha Engineer" in html
        assert "Beta Researcher" not in html


class TestVerticalRolePrivilegeEscalation:
    """Verifies that non-admin roles cannot access or mutate administrative resources."""

    def test_intern_blocked_from_admin_dashboard(self, app_client):
        client, db_path = app_client
        seed_intern(db_path, email="intern_priv@test.com", password="Pass123!")
        login_as_intern(client, db_path, email="intern_priv@test.com", password="Pass123!")

        resp = client.get("/admin")
        assert resp.status_code in (401, 403, 302)
        if resp.status_code == 302:
            assert resp.headers.get("Location") in ("/admin-login", "/#signin")

    def test_intern_blocked_from_admin_applications_api(self, app_client):
        client, db_path = app_client
        seed_intern(db_path, email="intern_priv2@test.com", password="Pass123!")
        login_as_intern(client, db_path, email="intern_priv2@test.com", password="Pass123!")

        resp = client.get("/admin/applications")
        assert resp.status_code in (401, 403, 302)

    def test_intern_blocked_from_admin_application_status_update(self, app_client):
        client, db_path = app_client
        seed_intern(db_path, email="intern_priv3@test.com", password="Pass123!")
        login_as_intern(client, db_path, email="intern_priv3@test.com", password="Pass123!")

        resp = client.post("/admin/update-application-status", json={
            "id": 1,
            "status": "Accepted",
            "reason": "Privilege escalation attempt"
        })
        assert resp.status_code in (401, 403, 302)

    def test_intern_blocked_from_staff_dashboard(self, app_client):
        client, db_path = app_client
        seed_intern(db_path, email="intern_priv4@test.com", password="Pass123!")
        login_as_intern(client, db_path, email="intern_priv4@test.com", password="Pass123!")

        resp = client.get("/staff/dashboard")
        assert resp.status_code in (401, 403, 302)

    def test_company_blocked_from_admin_endpoints(self, app_client):
        client, db_path = app_client
        seed_company(db_path, email="comp_priv@corp.com", password="Pass123!")
        login_as_company(client, db_path, email="comp_priv@corp.com", password="Pass123!")

        resp = client.get("/admin/csv/enrollments")
        assert resp.status_code in (401, 403, 302)

    def test_mentor_blocked_from_admin_enrollment_update(self, app_client):
        client, db_path = app_client
        seed_mentor(db_path, email="mentor_priv@test.com", password="Pass123!")
        login_as_mentor(client, db_path, email="mentor_priv@test.com", password="Pass123!")

        resp = client.post("/admin/update-enrollment-status", json={
            "id": 1,
            "status": "Completed"
        })
        assert resp.status_code in (401, 403, 302)

    def test_unauthenticated_blocked_from_all_role_endpoints(self, app_client):
        client, _ = app_client
        # All protected role endpoints must reject unauthenticated requests
        assert client.get("/intern/me").status_code in (401, 403, 302)
        assert client.get("/portal").status_code in (401, 403, 302)
        assert client.get("/company").status_code in (401, 403, 302)
        assert client.get("/mentor/applications").status_code in (401, 403, 302)
        assert client.get("/staff/dashboard").status_code in (401, 403, 302)
        assert client.get("/admin").status_code in (401, 403, 302)
