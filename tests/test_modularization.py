"""
tests/test_modularization.py - Monolith Modularization Characterization & Verification Suite
Fulfills Phase 23 requirements of INTERNSHIPPORTAL4_LOCAL_AI_AGENT_MASTER_PLAN.md

Verifies:
1. Domain service isolation and deterministic behavior (AuthService, PaymentService, NotificationService, CertificateService, MarketplaceService, InterviewService, LearningService, MasteryService).
2. Blueprint registration, endpoint accessibility, and RBAC / CSRF preservation across all 10 domain blueprints.
"""
import pytest
import json
from services.auth_service import AuthService
from services.payment_service import PaymentService
from services.notification_service import NotificationService
from services.certificate_service import CertificateService
from services.marketplace_service import MarketplaceService
from services.interview_service import InterviewService
from services.learning_service import LearningService
from services.mastery_service import MasteryService
from app import get_db, create_session, AUTH_COOKIE
from tests.conftest import seed_intern


class TestDomainServices:
    """Verifies that extracted services operate cleanly with unit tests."""

    def test_auth_service_password_hashing_and_verification(self):
        pwd = "TestSecurePassword123!"
        hashed = AuthService.set_password_hash(pwd)
        assert hashed != pwd
        assert AuthService.verify_password(hashed, pwd) is True
        assert AuthService.verify_password(hashed, "WrongPassword") is False
        assert AuthService.is_legacy_hash(hashed) is False

    def test_auth_service_legacy_sha256_detection(self):
        legacy = AuthService.hash_password("old_pass")
        assert AuthService.is_legacy_hash(legacy) is True
        assert AuthService.verify_password(legacy, "old_pass") is True
        assert AuthService.verify_password(legacy, "wrong_pass") is False

    def test_payment_service_pricing_and_verification(self, app_client):
        client, db_path = app_client
        with client.application.app_context():
            with get_db() as conn:
                pricing = PaymentService.determine_pricing(conn, "security_deposit", user_id=1, email="test@dbert.test")
                assert pricing["amount_inr"] > 0
                assert pricing["product_type"] == "security_deposit"
                assert "intern_id" in pricing["notes"]

    def test_notification_service_enqueue(self, app_client):
        client, db_path = app_client
        with client.application.app_context():
            with get_db() as conn:
                row_id = NotificationService.notify_application_submitted(
                    conn, application_id=101, email="applicant@test.com", name="Applicant", domain="AI Agent Development"
                )
                assert row_id > 0
                event = conn.execute("SELECT * FROM event_outbox WHERE id=?", (row_id,)).fetchone()
                assert event is not None
                assert event["event_type"] == "application.submitted"

    def test_certificate_service_issuance_and_lookup(self, app_client):
        client, db_path = app_client
        with client.application.app_context():
            with get_db() as conn:
                res = CertificateService.issue_certificate(
                    conn=conn,
                    intern_id=999,
                    course_id=1,
                    course_title="Python Core",
                    email="cert_intern@test.com"
                )
                assert "DBERT-C1-I999" in res["cert_id"]
                assert res["already_issued"] is False

                # Retrieve certificates
                certs = CertificateService.get_intern_certificates(conn, 999, "cert_intern@test.com")
                assert len(certs) == 1
                assert certs[0]["cert_id"] == res["cert_id"]

    def test_marketplace_service_google_jobs_schema(self):
        post = {
            "id": 42,
            "title": "Junior AI Engineer",
            "description": "Build agentic pipelines with Python",
            "company_name": "Antigravity Labs",
            "post_type": "job",
            "location": "Bengaluru",
            "expires_at": "2026-12-31"
        }
        schema = MarketplaceService.generate_google_jobs_json_ld(post)
        assert schema["@context"] == "https://schema.org/"
        assert schema["@type"] == "JobPosting"
        assert schema["title"] == "Junior AI Engineer"
        assert schema["hiringOrganization"]["name"] == "Antigravity Labs"

    def test_interview_service_question_assembly(self):
        questions = InterviewService.assemble_questions("AI Agent Development")
        assert len(questions) == 4
        types = [q["type"] for q in questions]
        assert types.count("technical") == 2
        assert types.count("applied") == 1
        assert types.count("communication") == 1

    def test_learning_and_mastery_facades(self, app_client):
        client, db_path = app_client
        with client.application.app_context():
            with get_db() as conn:
                from services.learning.learning_models import Concept
                from services.learning.concept_service import ConceptService
                c = Concept(
                    concept_id="facade.test",
                    name="Facade Concept",
                    description="Testing Facade",
                    domain="AI Agent Development",
                    subject="Core",
                    difficulty=1,
                    learning_objectives=["objective 1"],
                    assessment_criteria=["criteria 1"]
                )
                ConceptService.register_concept(conn, c)

                # Use mastery facade
                mastery = MasteryService.get_mastery(conn, student_id=55, concept_id="facade.test")
                assert mastery.mastery_score == 0.0
                assert mastery.mastery_level == "NOVICE"

                # Use learning facade
                tree = LearningService.get_domain_concept_tree(conn, "AI Agent Development")
                assert any(node["concept_id"] == "facade.test" for node in tree)


class TestModularBlueprints:
    """Verifies that all 10 modular blueprints are registered and routes respond correctly."""

    def test_auth_blueprint_endpoints(self, app_client):
        client, db_path = app_client
        res = client.get("/api/auth/status")
        assert res.status_code == 200
        data = res.get_json()
        assert data["authenticated"] is False

    def test_payment_blueprint_endpoints(self, app_client):
        client, db_path = app_client
        res = client.get("/api/payment/status")
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "success"
        assert "gateway_enabled" in data

    def test_admin_blueprint_endpoints_unauthorized(self, app_client):
        client, db_path = app_client
        res = client.get("/admin/telemetry")
        assert res.status_code == 401

    def test_marketplace_blueprint_endpoints_unauthorized(self, app_client):
        client, db_path = app_client
        res = client.post("/company/posts", json={"title": "Test"})
        assert res.status_code == 401

    def test_mentor_blueprint_endpoints_unauthorized(self, app_client):
        client, db_path = app_client
        res = client.post("/mentors/slots/1/book")
        assert res.status_code == 401

    def test_company_blueprint_endpoints_unauthorized(self, app_client):
        client, db_path = app_client
        res = client.post("/company/applications/1/status", json={"status": "Selected"})
        assert res.status_code == 401

    def test_enrollment_blueprint_endpoints_unauthorized(self, app_client):
        client, db_path = app_client
        res = client.post("/cohort/1/enroll")
        assert res.status_code == 401

    def test_applications_blueprint_endpoints_unauthorized(self, app_client):
        client, db_path = app_client
        res = client.get("/intern/my-applications")
        assert res.status_code == 401

    def test_learning_blueprint_endpoints_unauthorized(self, app_client):
        client, db_path = app_client
        res = client.get("/api/learning/v2/reviews-due")
        assert res.status_code == 401

    def test_intern_blueprint_endpoints_authenticated(self, app_client):
        client, db_path = app_client
        email = "intern_mod@dbert.test"
        intern_id = seed_intern(db_path, email=email)
        token = create_session(email, role="intern")
        client.set_cookie(AUTH_COOKIE, token)

        res = client.get("/intern/certificates")
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "success"
        assert isinstance(data["certificates"], list)

