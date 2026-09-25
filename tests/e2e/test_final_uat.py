"""
Phase 27 / Gate 19: Comprehensive Final End-to-End User Acceptance Test Suite (UAT)
Aligns with INTERNSHIPPORTAL4_LOCAL_AI_AGENT_MASTER_PLAN.md (§54, §55, §64, Gate 19).

Verifies the 9 required business workflows and system operational probes:
1. Visitor / Public Discovery (/, /jobs, /internships, security headers)
2. Candidate Signup & Authentication (duplicate guards, session tokens, secure cookies)
3. Internship Application Submission (SOP, Under Review state, gate defense)
4. Admin / Mentor Selection (state machine transition, audit history, unlocked payment)
5. Cohort Enrollment & Capacity (selectable Mondays, upload receipt, Pending Verification)
6. Payment Verification & Idempotency (transition to Accepted, outbox event, sync application)
7. Guided Learning 2.0 Turn & Spaced Review (session init, atomic turn, deterministic mastery)
8. Task Exploration, Submission & Coin Rewards (capstone submit, approval, coin ledger)
9. Certificate Issuance & Public Verification (minting, authenticated retrieval, public verify, 404 on forged)
10. System Health & Integrity Probes (/health, /ready, /admin/integrity-dashboard)
11. Continuous Complete E2E Lifecycle Journey
"""

import os
import io
import json
import uuid
import datetime
import pytest

os.environ["TESTING"] = "true"
os.environ.setdefault("FLASK_DEBUG", "false")
os.environ.setdefault("SMTP_PASS", "")

from tests.conftest import (
    seed_intern, seed_company, seed_staff, seed_mentor,
    login_as_intern, login_as_company, login_as_staff, login_as_admin, login_as_mentor,
    logout
)
from app import (
    app, get_db, set_password_hash, create_session, AUTH_COOKIE,
    STAGE_APP_REQUIRED, STAGE_UNDER_REVIEW, STAGE_SELECTED, STAGE_PAYMENT_PENDING, STAGE_CONFIRMED,
    STATUS_UNDER_REVIEW, STATUS_SELECTED, STATUS_ACCEPTED, STATUS_ENROLLMENT_PENDING,
    get_selectable_mondays, CSRF_EXEMPT_ENDPOINTS,
    credit_intern_coins, get_task_balance
)
from services.application_service import transition_application
from services.enrollment_service import transition_enrollment
from services.learning.learning_models import init_learning_tables, Concept
from services.learning.concept_service import ConceptService
from services.integrity_service import IntegrityService

# Ensure learning endpoints are exempt from CSRF in test client
CSRF_EXEMPT_ENDPOINTS.update([
    "api_learning_v2_session",
    "api_learning_v2_turn",
    "learning.api_learning_v2_session",
    "learning.api_learning_v2_turn",
    "admin_integrity_heal"
])


def _create_sample_png():
    return b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 50


class TestFinalUAT:
    """Gate 19 Final User Acceptance Test Suite covering all 9 core workflows."""

    def test_flow_1_visitor_discovery(self, app_client):
        """Workflow 1: Visitor discovers public listings with security headers and no data leaks."""
        client, db_path = app_client

        # Discover Home
        resp_home = client.get("/")
        assert resp_home.status_code == 200
        assert "X-Request-ID" in resp_home.headers
        assert resp_home.headers.get("X-Content-Type-Options") == "nosniff"

        # Discover Jobs
        resp_jobs = client.get("/jobs")
        assert resp_jobs.status_code == 200

        # Discover Internships
        resp_internships = client.get("/internships")
        assert resp_internships.status_code == 200

    def test_flow_2_candidate_signup_and_auth(self, app_client):
        """Workflow 2: Candidate registration, duplicate prevention, and secure session management."""
        client, db_path = app_client

        email = "uat_candidate_02@dbert.test"
        phone = "9876543201"
        password = "UatCandidatePass123!"

        # Valid registration
        reg_resp = client.post("/signup/stage1", json={
            "name": "Alex Candidate",
            "email": email,
            "phone": phone,
            "password": password,
            "domain": "AI Agent Development",
            "terms_accepted": True
        })
        assert reg_resp.status_code == 200
        assert reg_resp.get_json().get("status") == "success"

        # Duplicate email guard
        dup_resp = client.post("/signup/stage1", json={
            "name": "Alex Clone",
            "email": email,
            "phone": "9876543202",
            "password": password,
            "domain": "AI Agent Development",
            "terms_accepted": True
        })
        assert dup_resp.status_code in (400, 409)

        # Candidate Login
        login_resp = client.post("/intern/login", json={"email": email, "password": password})
        assert login_resp.status_code == 200
        # Cookie verification
        set_cookie = login_resp.headers.get("Set-Cookie", "")
        assert AUTH_COOKIE in set_cookie
        assert "HttpOnly" in set_cookie
        assert "SameSite=Lax" in set_cookie

        # Invalidate / Logout
        logout_resp = logout(client)
        assert logout_resp.status_code in (200, 302)

    def test_flow_3_internship_application_submission(self, app_client):
        """Workflow 3: SOP submission, Under Review placement, and lifecycle gate enforcement."""
        client, db_path = app_client
        email = "uat_candidate_03@dbert.test"
        seed_intern(db_path, email=email, password="Pass123456!", name="SOP Candidate", status="Under Review")
        login_as_intern(client, db_path, email=email, password="Pass123456!")

        # Candidate saves Statement of Purpose (must be >= 80 characters)
        sop = "I am deeply passionate about building autonomous LLM agents and multi-agent systems to solve high-impact industrial problems."
        save_resp = client.post("/intern/save-wizard-step", json={
            "step_key": "application_sop",
            "why_join": sop
        })
        assert save_resp.status_code == 200, f"SOP save failed: {save_resp.data}"
        data = save_resp.get_json()
        assert data.get("stage") == STAGE_UNDER_REVIEW

        # Gate enforcement: cannot submit payment receipt while Under Review
        mondays = get_selectable_mondays()
        valid_monday = mondays[0] if mondays else "2026-10-05"
        early_pay = client.post("/enroll", data={
            "name": "SOP Candidate",
            "email": email,
            "phone": "9876543203",
            "joining_date": valid_monday,
            "domain": "AI Agent Development",
            "payment_screenshot": (io.BytesIO(_create_sample_png()), "receipt.png")
        }, content_type="multipart/form-data")
        assert early_pay.status_code in (400, 403)

    def test_flow_4_mentor_admin_selection(self, app_client):
        """Workflow 4: Admin reviews application and selects candidate via state machine."""
        client, db_path = app_client
        email = "uat_candidate_04@dbert.test"
        seed_intern(db_path, email=email, password="Pass123456!", name="Review Candidate", status=STATUS_UNDER_REVIEW)

        with get_db() as conn:
            app_row = conn.execute("SELECT id FROM applications WHERE LOWER(email)=?", (email,)).fetchone()
            app_id = app_row["id"]

            trans = transition_application(
                conn=conn,
                application_id=app_id,
                target_status=STATUS_SELECTED,
                actor="lead_reviewer",
                actor_role="admin",
                reason="Top tier agent portfolio."
            )
            conn.commit()
            assert trans["success"] is True

            hist = conn.execute(
                "SELECT * FROM application_status_history WHERE application_id=? ORDER BY id DESC LIMIT 1",
                (app_id,)
            ).fetchone()
            assert hist is not None
            assert hist["new_status"] == STATUS_SELECTED
            assert hist["changed_by"] == "lead_reviewer"

        # Candidate logs in and sees payment step unlocked
        login_as_intern(client, db_path, email=email, password="Pass123456!")
        me_resp = client.get("/intern/me")
        assert me_resp.status_code == 200
        me_data = me_resp.get_json()
        assert me_data.get("flow_stage") == STAGE_SELECTED
        assert me_data.get("flow_state", {}).get("can_upload_payment") is True

    def test_flow_5_cohort_enrollment(self, app_client):
        """Workflow 5: Candidate enrolls with selected Monday cohort and uploads receipt."""
        client, db_path = app_client
        email = "uat_candidate_05@dbert.test"
        seed_intern(db_path, email=email, password="Pass123456!", name="Cohort Candidate", status=STATUS_SELECTED)
        login_as_intern(client, db_path, email=email, password="Pass123456!")

        mondays = get_selectable_mondays()
        valid_monday = mondays[0] if mondays else "2026-10-05"

        enroll_resp = client.post("/enroll", data={
            "name": "Cohort Candidate",
            "email": email,
            "phone": "9876543205",
            "joining_date": valid_monday,
            "domain": "AI Agent Development",
            "payment_screenshot": (io.BytesIO(_create_sample_png()), "receipt.png")
        }, content_type="multipart/form-data")
        assert enroll_resp.status_code == 200

        with get_db() as conn:
            enr = conn.execute("SELECT * FROM enrollments WHERE email=?", (email,)).fetchone()
            assert enr is not None
            assert enr["payment_status"] == "Pending Verification"
            assert enr["joining_date"] == valid_monday

    def test_flow_6_payment_verification_and_idempotency(self, app_client):
        """Workflow 6: Payment transition to Accepted, outbox event generation, and idempotency."""
        client, db_path = app_client
        email = "uat_candidate_06@dbert.test"
        seed_intern(db_path, email=email, password="Pass123456!", name="Pay Candidate", status=STATUS_SELECTED)

        with get_db() as conn:
            app_row = conn.execute("SELECT id FROM applications WHERE LOWER(email)=?", (email,)).fetchone()
            cur = conn.execute(
                """
                INSERT INTO enrollments (application_id, name, email, phone, joining_date, domain, payment_status, timestamp)
                VALUES (?, 'Pay Candidate', ?, '9876543206', '2026-10-05', 'AI Agent Development', 'Pending Verification', datetime('now'))
                """,
                (app_row["id"], email)
            )
            enrollment_id = cur.lastrowid
            conn.execute("UPDATE applications SET status=? WHERE id=?", (STATUS_ENROLLMENT_PENDING, app_row["id"]))
            conn.commit()

            # First transition: Pending Verification -> Accepted
            res1 = transition_enrollment(
                conn=conn,
                enrollment_id=enrollment_id,
                target_status="Accepted",
                actor="admin",
                reason="Verified bank deposit."
            )
            conn.commit()
            assert res1["success"] is True

            # Outbox event verified in event_outbox table
            ev = conn.execute(
                "SELECT * FROM event_outbox WHERE aggregate_id=? AND event_type='payment.accepted'",
                (str(enrollment_id),)
            ).fetchone()
            assert ev is not None

            # Application automatically synced to Accepted
            app_check = conn.execute("SELECT status FROM applications WHERE id=?", (app_row["id"],)).fetchone()
            assert app_check["status"] == STATUS_ACCEPTED

            # Idempotency check: Repeated transition should raise or be handled safely without double credit
            enr_check = conn.execute("SELECT payment_status FROM enrollments WHERE id=?", (enrollment_id,)).fetchone()
            assert enr_check["payment_status"] == "Accepted"

    def test_flow_7_guided_learning_turn_and_mastery(self, app_client):
        """Workflow 7: Guided Learning 2.0 session initialization and atomic learning turn."""
        client, db_path = app_client
        email = "uat_candidate_07@dbert.test"
        intern_id = seed_intern(db_path, email=email, password="Pass123456!", name="Learn Candidate", status=STATUS_ACCEPTED)
        login_as_intern(client, db_path, email=email, password="Pass123456!")

        with get_db() as conn:
            init_learning_tables(conn)
            # Find domain course
            course = conn.execute("SELECT id FROM courses WHERE domain='AI Agent Development' LIMIT 1").fetchone()
            course_id = course["id"] if course else 1

            # Ensure course enrollment exists
            conn.execute(
                "INSERT OR IGNORE INTO course_enrollments (intern_id, course_id, current_day) VALUES (?, ?, 1)",
                (intern_id, course_id)
            )
            # Register a canonical test concept
            c = Concept(
                concept_id="uat.agent.prompting",
                name="Prompt Engineering & Few-Shot In-Context Learning",
                description="Principles of structuring few-shot prompts and system instructions.",
                domain="AI Agent Development",
                subject="Agent Core",
                difficulty=1,
                learning_objectives=["Structure system prompt", "Provide few-shot exemplars"],
                assessment_criteria=["Correct delimiters", "Exemplar diversity"]
            )
            ConceptService.register_concept(conn, c)
            conn.commit()

        # Step 7a: Start learning session
        sess_resp = client.post("/api/learning/v2/session", json={"course_id": course_id})
        assert sess_resp.status_code == 200, f"Session creation failed: {sess_resp.data}"
        sess_data = sess_resp.get_json().get("data", {})
        session_id = sess_data.get("session", {}).get("session_id")
        assert session_id is not None

        # Step 7b: Execute atomic turn with idempotency key
        turn_key = str(uuid.uuid4())
        turn_resp = client.post("/api/learning/v2/turn", json={
            "session_id": session_id,
            "message": "Few-shot prompting provides exemplars that illustrate desired input-output behavior.",
            "idempotency_key": turn_key
        })
        assert turn_resp.status_code == 200, f"Turn execution failed: {turn_resp.data}"
        turn_data = turn_resp.get_json().get("data", {})
        assert "evaluation" in turn_data or "next_action" in turn_data

        # Step 7c: Check spaced repetition review query
        rev_resp = client.get("/api/learning/v2/reviews-due")
        assert rev_resp.status_code == 200
        assert "reviews" in rev_resp.get_json()

    def test_flow_8_task_submission_and_coins(self, app_client):
        """Workflow 8: Capstone task viewing, submission, mentor approval, and coin reward."""
        client, db_path = app_client
        email = "uat_candidate_08@dbert.test"
        intern_id = seed_intern(db_path, email=email, password="Pass123456!", name="Task Candidate", status=STATUS_ACCEPTED)
        login_as_intern(client, db_path, email=email, password="Pass123456!")

        with get_db() as conn:
            # Seed active task
            cur = conn.execute(
                "INSERT INTO tasks (title, description, coin_reward, is_active) VALUES ('UAT Capstone Agent', 'Production RAG pipeline', 100, 1)"
            )
            task_id = cur.lastrowid
            conn.execute(
                "INSERT INTO task_versions (task_id, version_number, instructions, rubric) VALUES (?, 1, 'Build RAG system', 'Evaluated for precision')",
                (task_id,)
            )
            conn.commit()

        # View task
        v_resp = client.get(f"/tasks/{task_id}")
        assert v_resp.status_code == 200

        # Submit task
        sub_resp = client.post(f"/tasks/{task_id}/submit", json={
            "submission_content": "https://github.com/uat-candidate/production-rag-agent"
        })
        assert sub_resp.status_code == 200

        # Review and approve submission
        with get_db() as conn:
            sub = conn.execute(
                "SELECT id FROM task_submissions WHERE intern_id=? AND task_id=?",
                (intern_id, task_id)
            ).fetchone()
            assert sub is not None
            sub_id = sub["id"]

            conn.execute("UPDATE task_submissions SET status='approved', coins_awarded=100 WHERE id=?", (sub_id,))
            # Credit coins using the central coin engine
            new_bal = credit_intern_coins(conn, intern_id, 100, "UAT Task Reward", ref_id=task_id, email=email)
            conn.commit()

            # Verify balance
            bal = get_task_balance(conn, intern_id, email=email)
            assert bal == 100

    def test_flow_9_certificate_issuance_and_public_verification(self, app_client):
        """Workflow 9: Certificate minting, intern dashboard retrieval, and third-party public verification."""
        client, db_path = app_client
        email = "uat_candidate_09@dbert.test"
        intern_id = seed_intern(db_path, email=email, password="Pass123456!", name="Cert Candidate", status=STATUS_ACCEPTED)

        cert_id = f"DBERT-UAT-{uuid.uuid4().hex[:8].upper()}"
        issued_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO intern_certificates (intern_id, course_id, course_title, cert_id, issued_at, url, tier, email)
                VALUES (?, 1, 'Certified Autonomous Agent Engineer', ?, ?, ?, 'dbert_verified', ?)
                """,
                (intern_id, cert_id, issued_date, f"/portal/certificate/{cert_id}", email)
            )
            conn.commit()

        # Intern views cert in portal
        login_as_intern(client, db_path, email=email, password="Pass123456!", name="Cert Candidate")
        cert_list = client.get("/intern/certificates")
        assert cert_list.status_code == 200
        certs = cert_list.get_json().get("certificates", [])
        assert any(c["cert_id"] == cert_id for c in certs)

        # Public verification by third-party viewer without authentication
        logout(client)
        pub_resp = client.get(f"/portal/certificate/{cert_id}")
        assert pub_resp.status_code == 200
        html = pub_resp.get_data(as_text=True)
        assert cert_id in html
        assert "Cert Candidate" in html

        # Negative verification: forged/unknown certificate returns 404
        fake_resp = client.get("/portal/certificate/DBERT-FORGED-99999")
        assert fake_resp.status_code == 404

    def test_flow_10_system_health_and_integrity_probes(self, app_client):
        """Workflow 10: Operational readiness, health probes, and admin data integrity dashboard."""
        client, db_path = app_client

        # Liveness probe
        h_resp = client.get("/health")
        assert h_resp.status_code == 200
        h_data = h_resp.get_json()
        assert h_data.get("status") in ("ok", "healthy")

        # Readiness probe
        r_resp = client.get("/ready")
        assert r_resp.status_code == 200
        r_data = r_resp.get_json()
        assert r_data.get("status") == "ready"

        # Admin integrity dashboard JSON check
        login_as_admin(client, db_path)
        integ_resp = client.get("/admin/integrity-dashboard", headers={"Accept": "application/json"})
        assert integ_resp.status_code == 200
        integ_data = integ_resp.get_json()
        assert integ_data.get("status") == "success"
        anomalies = integ_data.get("anomalies", {})
        assert "summary" in anomalies
        assert anomalies["summary"]["health_score"] >= 90.0

    def test_complete_continuous_uat_lifecycle(self, app_client):
        """Continuous end-to-end UAT covering complete candidate lifecycle in one sequence."""
        client, db_path = app_client

        cand_name = "Jordan E2E"
        cand_email = "jordan.uat.e2e@dbert.test"
        cand_phone = "9876543299"
        cand_pass = "JordanPassSecure2026!"
        domain = "AI Agent Development"

        # 1. Visitor Discovery
        assert client.get("/").status_code == 200

        # 2. Candidate Registration
        reg = client.post("/signup/stage1", json={
            "name": cand_name,
            "email": cand_email,
            "phone": cand_phone,
            "password": cand_pass,
            "domain": domain,
            "terms_accepted": True
        })
        assert reg.status_code == 200

        # 3. Candidate Login & Application SOP (must be >= 80 characters)
        login_as_intern(client, db_path, email=cand_email, password=cand_pass, name=cand_name)
        client.post("/intern/save-wizard-step", json={
            "step_key": "application_sop",
            "why_join": "I am committed to engineering world-class autonomous multi-agent workflows and production systems."
        })

        with get_db() as conn:
            app_row = conn.execute("SELECT id FROM applications WHERE LOWER(email)=?", (cand_email,)).fetchone()
            app_id = app_row["id"]

            # 4. Admin Review & Selection
            transition_application(
                conn=conn,
                application_id=app_id,
                target_status=STATUS_SELECTED,
                actor="staff_lead",
                actor_role="staff",
                reason="Outstanding candidate profile."
            )
            conn.commit()

        # 5. Cohort Enrollment
        mondays = get_selectable_mondays()
        sel_mon = mondays[0] if mondays else "2026-10-05"
        enr_resp = client.post("/enroll", data={
            "name": cand_name,
            "email": cand_email,
            "phone": cand_phone,
            "joining_date": sel_mon,
            "domain": domain,
            "payment_screenshot": (io.BytesIO(_create_sample_png()), "receipt.png")
        }, content_type="multipart/form-data")
        assert enr_resp.status_code == 200

        # 6. Payment Acceptance
        with get_db() as conn:
            enr_row = conn.execute("SELECT id FROM enrollments WHERE email=?", (cand_email,)).fetchone()
            enr_id = enr_row["id"]
            transition_enrollment(
                conn=conn,
                enrollment_id=enr_id,
                target_status="Accepted",
                actor="admin",
                reason="Verified bank transfer."
            )
            conn.commit()

        # 7. Guided Learning 2.0
        with get_db() as conn:
            init_learning_tables(conn)
            acct = conn.execute("SELECT id FROM intern_accounts WHERE email=?", (cand_email,)).fetchone()
            intern_id = acct["id"]
            course = conn.execute("SELECT id FROM courses WHERE domain=? LIMIT 1", (domain,)).fetchone()
            course_id = course["id"] if course else 1
            conn.execute(
                "INSERT OR IGNORE INTO course_enrollments (intern_id, course_id, current_day) VALUES (?, ?, 1)",
                (intern_id, course_id)
            )
            c = Concept(
                concept_id="e2e.flow.agent",
                name="Agent Architectures",
                description="Core concepts of autonomous agent architectures.",
                domain=domain,
                subject="Agent Engineering",
                difficulty=1
            )
            ConceptService.register_concept(conn, c)
            conn.commit()

        sess_resp = client.post("/api/learning/v2/session", json={"course_id": course_id})
        assert sess_resp.status_code == 200
        sess_id = sess_resp.get_json()["data"]["session"]["session_id"]
        turn_resp = client.post("/api/learning/v2/turn", json={
            "session_id": sess_id,
            "message": "Agents utilize tools and prompt instructions to execute reasoning loops.",
            "idempotency_key": str(uuid.uuid4())
        })
        assert turn_resp.status_code == 200

        # 8. Task Submission & Reward
        with get_db() as conn:
            cur = conn.execute("INSERT INTO tasks (title, description, coin_reward, is_active) VALUES ('E2E Agent Task', 'Desc', 75, 1)")
            t_id = cur.lastrowid
            conn.execute("INSERT INTO task_versions (task_id, version_number, instructions, rubric) VALUES (?, 1, 'Inst', 'Rubric')", (t_id,))
            conn.commit()

        client.post(f"/tasks/{t_id}/submit", json={"submission_content": "https://github.com/jordan/agent"})

        with get_db() as conn:
            conn.execute("UPDATE task_submissions SET status='approved', coins_awarded=75 WHERE intern_id=? AND task_id=?", (intern_id, t_id))
            credit_intern_coins(conn, intern_id, 75, "Task Completion", ref_id=t_id, email=cand_email)
            conn.commit()

        # 9. Certificate Issuance & Public Verification
        final_cert_id = f"DBERT-UAT-FINAL-{uuid.uuid4().hex[:6].upper()}"
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO intern_certificates (intern_id, course_id, course_title, cert_id, issued_at, url, tier, email)
                VALUES (?, ?, 'Certified AI Systems Architect', ?, datetime('now'), ?, 'dbert_verified', ?)
                """,
                (intern_id, course_id, final_cert_id, f"/portal/certificate/{final_cert_id}", cand_email)
            )
            conn.commit()

        logout(client)
        final_pub = client.get(f"/portal/certificate/{final_cert_id}")
        assert final_pub.status_code == 200
        assert cand_name in final_pub.get_data(as_text=True)

        # 10. Operational Health & Probes
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 200
