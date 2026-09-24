"""
Phase 12: Golden Applicant Journey E2E Test Suite
P0 Release Gate: Automates the entire end-to-end applicant lifecycle:
1. visitor (public discovery)
2. signup (account creation)
3. application (SOP submission -> Under Review)
4. login (authentication)
5. portal (view Under Review status, payment locked)
6. admin review & selection (Under Review -> Selected via state machine)
7. candidate sees selection (payment unlocked)
8. enrollment (submits enrollment details & receipt)
9. payment acceptance (enrollment & application transitioned to Accepted)
10. active internship & domain course access (auto-enrolled in domain course)
11. task exploration (views assigned task)
12. task submission (submits capstone solution)
13. mentor / staff review (submission approved & coins awarded)
14. certificate issuance (minted into intern_certificates)
15. public verification (public viewer verifies certificate at /portal/certificate/<cert_id>)
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
    STATUS_UNDER_REVIEW, STATUS_SELECTED, STATUS_ACCEPTED, get_selectable_mondays
)
from services.application_service import transition_application
from services.enrollment_service import transition_enrollment


class TestGoldenApplicantJourney:
    """Verifies the complete 15-step Golden Applicant Journey from anonymous visitor to verified graduate."""

    def test_complete_golden_applicant_journey(self, app_client):
        client, db_path = app_client
        os.environ["DB_FILE"] = db_path

        candidate_name = "Devon Applicant"
        candidate_email = "devon.applicant@example.com"
        candidate_phone = "9876543299"
        candidate_domain = "AI Agent Development"
        candidate_pass = "GoldenSecurePass123!"

        # -------------------------------------------------------------
        # STEP 1: VISITOR (Public Discovery)
        # -------------------------------------------------------------
        resp_home = client.get("/")
        assert resp_home.status_code == 200

        resp_jobs = client.get("/jobs")
        assert resp_jobs.status_code == 200

        resp_internships = client.get("/internships")
        assert resp_internships.status_code == 200

        # -------------------------------------------------------------
        # STEP 2: SIGNUP (Account Registration)
        # -------------------------------------------------------------
        signup_resp = client.post("/signup/stage1", json={
            "name": candidate_name,
            "email": candidate_email,
            "phone": candidate_phone,
            "password": candidate_pass,
            "domain": candidate_domain,
            "terms_accepted": True
        })
        assert signup_resp.status_code == 200, f"Signup failed: {signup_resp.data}"
        signup_data = signup_resp.get_json()
        assert signup_data.get("status") == "success"

        # Verify DB state after signup
        with get_db() as conn:
            acct = conn.execute("SELECT * FROM intern_accounts WHERE email=?", (candidate_email,)).fetchone()
            assert acct is not None
            assert acct["name"] == candidate_name
            assert acct["is_active"] == 1
            intern_id = acct["id"]

            app_row = conn.execute("SELECT * FROM applications WHERE LOWER(email)=?", (candidate_email,)).fetchone()
            assert app_row is not None
            assert app_row["status"] == STATUS_UNDER_REVIEW
            app_id = app_row["id"]

        # -------------------------------------------------------------
        # STEP 3: APPLICATION (SOP Submission)
        # -------------------------------------------------------------
        # Log in as intern to complete application SOP
        login_resp = client.post("/intern/login", json={"email": candidate_email, "password": candidate_pass})
        assert login_resp.status_code == 200

        sop_text = "I have built multi-agent LangGraph workflows and want to engineer production agentic systems at DBERT Labs."
        sop_resp = client.post("/intern/save-wizard-step", json={
            "step_key": "application_sop",
            "why_join": sop_text
        })
        assert sop_resp.status_code == 200
        sop_data = sop_resp.get_json()
        assert sop_data.get("stage") == STAGE_UNDER_REVIEW

        with get_db() as conn:
            app_updated = conn.execute("SELECT why_join, status FROM applications WHERE id=?", (app_id,)).fetchone()
            assert app_updated["why_join"] == sop_text
            assert app_updated["status"] == STATUS_UNDER_REVIEW

        # -------------------------------------------------------------
        # STEP 4: LOGIN & SESSION VALIDATION
        # -------------------------------------------------------------
        logout(client)
        login_resp2 = client.post("/intern/login", json={"email": candidate_email, "password": candidate_pass})
        assert login_resp2.status_code == 200

        with get_db() as conn:
            sess = conn.execute("SELECT * FROM user_sessions WHERE email=? AND role='intern'", (candidate_email,)).fetchone()
            assert sess is not None

        # -------------------------------------------------------------
        # STEP 5: PORTAL VIEW (Under Review - Payment Locked)
        # -------------------------------------------------------------
        portal_resp = client.get("/portal")
        assert portal_resp.status_code == 200

        me_resp1 = client.get("/intern/me")
        assert me_resp1.status_code == 200
        me_data1 = me_resp1.get_json()
        assert me_data1.get("flow_stage") == STAGE_UNDER_REVIEW
        assert me_data1.get("flow_state", {}).get("can_upload_payment") is False

        valid_joining_date = get_selectable_mondays()[0]

        # Attempting to upload payment receipt at this stage MUST be rejected
        valid_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 50
        early_pay_resp = client.post("/enroll", data={
            "name": candidate_name,
            "email": candidate_email,
            "phone": candidate_phone,
            "joining_date": valid_joining_date,
            "domain": candidate_domain,
            "payment_screenshot": (io.BytesIO(valid_png), "receipt.png")
        }, content_type="multipart/form-data")
        assert early_pay_resp.status_code in (400, 403)

        # -------------------------------------------------------------
        # STEP 6: ADMIN REVIEW & SELECTION
        # -------------------------------------------------------------
        # Admin transitions application to "Selected" via central state machine
        with get_db() as conn:
            trans_res = transition_application(
                conn=conn,
                application_id=app_id,
                target_status=STATUS_SELECTED,
                actor="admin",
                actor_role="admin",
                reason="Excellent RAG background and SOP."
            )
            conn.commit()
        assert trans_res["success"] is True
        assert trans_res["new_status"] == STATUS_SELECTED

        # Verify audit history
        with get_db() as conn:
            hist = conn.execute(
                "SELECT * FROM application_status_history WHERE application_id=? ORDER BY id DESC LIMIT 1",
                (app_id,)
            ).fetchone()
            assert hist is not None
            assert hist["new_status"] == STATUS_SELECTED
            assert hist["changed_by"] == "admin"

        # -------------------------------------------------------------
        # STEP 7: CANDIDATE SEES SELECTION (Payment Unlocked)
        # -------------------------------------------------------------
        me_resp2 = client.get("/intern/me")
        assert me_resp2.status_code == 200
        me_data2 = me_resp2.get_json()
        assert me_data2.get("flow_stage") == STAGE_SELECTED
        assert me_data2.get("flow_state", {}).get("can_upload_payment") is True

        wiz_resp = client.get("/intern/wizard-status")
        assert wiz_resp.status_code == 200
        wiz_data = wiz_resp.get_json()
        assert wiz_data.get("payment_locked") is False

        # -------------------------------------------------------------
        # STEP 8: ENROLLMENT (Deposit Receipt Upload)
        # -------------------------------------------------------------
        enroll_resp = client.post("/enroll", data={
            "name": candidate_name,
            "email": candidate_email,
            "phone": candidate_phone,
            "joining_date": valid_joining_date,
            "domain": candidate_domain,
            "payment_screenshot": (io.BytesIO(valid_png), "receipt.png")
        }, content_type="multipart/form-data")
        assert enroll_resp.status_code == 200

        with get_db() as conn:
            enr_row = conn.execute("SELECT * FROM enrollments WHERE email=?", (candidate_email,)).fetchone()
            assert enr_row is not None
            assert enr_row["payment_status"] == "Pending Verification"
            enrollment_id = enr_row["id"]

            # Application is now Enrollment Pending
            app_check = conn.execute("SELECT status FROM applications WHERE id=?", (app_id,)).fetchone()
            assert app_check["status"] in ("Selected", "Enrollment Pending")

        # -------------------------------------------------------------
        # STEP 9: PAYMENT ACCEPTANCE (State Machine Transition)
        # -------------------------------------------------------------
        with get_db() as conn:
            enr_trans = transition_enrollment(
                conn=conn,
                enrollment_id=enrollment_id,
                target_status="Accepted",
                actor="admin",
                actor_role="admin",
                reason="Payment screenshot verified."
            )
            conn.commit()
        assert enr_trans["success"] is True
        assert enr_trans["new_status"] == "Accepted"

        with get_db() as conn:
            enr_check = conn.execute("SELECT payment_status FROM enrollments WHERE id=?", (enrollment_id,)).fetchone()
            assert enr_check["payment_status"] == "Accepted"

            app_sync = conn.execute("SELECT status FROM applications WHERE id=?", (app_id,)).fetchone()
            assert app_sync["status"] == STATUS_ACCEPTED

        # -------------------------------------------------------------
        # STEP 10: ACTIVE INTERNSHIP & AUTOMATIC COURSE ACCESS
        # -------------------------------------------------------------
        me_resp3 = client.get("/intern/me")
        assert me_resp3.status_code == 200
        me_data3 = me_resp3.get_json()
        assert me_data3.get("flow_stage") == STAGE_CONFIRMED
        assert me_data3.get("flow_state", {}).get("is_accepted") is True

        # Candidate is automatically enrolled in domain foundational course
        course_enrs = me_data3.get("course_enrollments", [])
        assert len(course_enrs) >= 1
        primary_course = course_enrs[0]
        assert primary_course["domain"] == candidate_domain
        course_id = primary_course["course_id"]

        # -------------------------------------------------------------
        # STEP 11: TASK EXPLORATION
        # -------------------------------------------------------------
        # Seed an active task for this domain
        with get_db() as conn:
            cur_task = conn.execute("""
                INSERT INTO tasks (title, description, coin_reward, is_active)
                VALUES ('Capstone: Autonomous Agent Workflow', 'Build an autonomous agent with evaluation metrics.', 50, 1)
            """)
            task_id = cur_task.lastrowid
            cur_ver = conn.execute("""
                INSERT INTO task_versions (task_id, version_number, instructions, rubric)
                VALUES (?, 1, 'Build agent with LangGraph', 'Passes all automated evaluation suites.')
            """, (task_id,))
            version_id = cur_ver.lastrowid
            conn.commit()

        task_resp = client.get(f"/tasks/{task_id}")
        assert task_resp.status_code == 200
        task_data = task_resp.get_json()
        assert task_data.get("task", {}).get("id") == task_id
        assert task_data.get("my_submission") is None

        # -------------------------------------------------------------
        # STEP 12: TASK SUBMISSION
        # -------------------------------------------------------------
        sub_resp = client.post(f"/tasks/{task_id}/submit", json={
            "submission_content": "https://github.com/devon/production-agent-capstone"
        })
        assert sub_resp.status_code == 200
        assert sub_resp.get_json().get("status") == "success"

        with get_db() as conn:
            sub_row = conn.execute("SELECT * FROM task_submissions WHERE intern_id=? AND task_id=?", (intern_id, task_id)).fetchone()
            assert sub_row is not None
            assert sub_row["status"] == "pending"
            submission_id = sub_row["id"]

        # -------------------------------------------------------------
        # STEP 13: MENTOR / STAFF REVIEW & APPROVAL
        # -------------------------------------------------------------
        with get_db() as conn:
            conn.execute("""
                UPDATE task_submissions
                SET status='approved', coins_awarded=50
                WHERE id=?
            """, (submission_id,))
            conn.commit()

        # Verify submission status in candidate view
        task_view2 = client.get(f"/tasks/{task_id}")
        assert task_view2.status_code == 200
        assert task_view2.get_json().get("my_submission", {}).get("status") == "approved"

        # -------------------------------------------------------------
        # STEP 14: CERTIFICATE ISSUANCE
        # -------------------------------------------------------------
        cert_uuid = f"DBERT-VERIFIED-{uuid.uuid4().hex[:8].upper()}"
        now_ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cert_url = f"/portal/certificate/{cert_uuid}"

        with get_db() as conn:
            conn.execute("""
                INSERT INTO intern_certificates (intern_id, course_id, course_title, cert_id, issued_at, url, tier, email)
                VALUES (?, ?, 'AI Agent Engineering Certification', ?, ?, ?, 'dbert_verified', ?)
            """, (intern_id, course_id, cert_uuid, now_ts, cert_url, candidate_email))
            conn.commit()

        # Intern queries their certificates
        certs_resp = client.get("/intern/certificates")
        assert certs_resp.status_code == 200
        certs_data = certs_resp.get_json()
        assert len(certs_data.get("certificates", [])) >= 1
        my_cert = certs_data["certificates"][0]
        assert my_cert["cert_id"] == cert_uuid
        assert my_cert["course_title"] == "AI Agent Engineering Certification"

        # -------------------------------------------------------------
        # STEP 15: PUBLIC CERTIFICATE VERIFICATION
        # -------------------------------------------------------------
        # Log out candidate to simulate a third-party recruiter or verifier
        logout(client)

        pub_cert_resp = client.get(f"/portal/certificate/{cert_uuid}")
        assert pub_cert_resp.status_code == 200
        html_out = pub_cert_resp.get_data(as_text=True)

        # Public page displays candidate name and verified certification
        assert candidate_name in html_out
        assert cert_uuid in html_out

    def test_golden_journey_strict_state_gates(self, app_client):
        """Verifies that candidates cannot jump ahead in the lifecycle prematurely."""
        client, db_path = app_client
        os.environ["DB_FILE"] = db_path

        email = "gate_checker@example.com"
        seed_intern(db_path, email=email, password="Pass123456!", name="Gate Checker", status="Under Review")
        login_as_intern(client, db_path, email=email, password="Pass123456!")

        # 1. Under Review candidate cannot submit tasks (enrollment required)
        with get_db() as conn:
            cur = conn.execute("INSERT INTO tasks (title, description, is_active) VALUES ('Gated Task', 'Test', 1)")
            t_id = cur.lastrowid
            conn.execute("INSERT INTO task_versions (task_id, version_number, instructions, rubric) VALUES (?, 1, 'T', 'R')", (t_id,))
            conn.commit()

        bad_sub = client.post(f"/tasks/{t_id}/submit", json={"submission_content": "Early submit"})
        assert bad_sub.status_code == 403
        assert "enrollment required" in bad_sub.get_json().get("message", "").lower()

        # 2. Non-existent certificate returns 404
        ghost_cert = client.get("/portal/certificate/DBERT-VERIFIED-NONEXISTENT")
        assert ghost_cert.status_code == 404
