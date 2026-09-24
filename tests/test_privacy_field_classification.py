"""
Phase 16: Privacy & Field Classification Test Suite
Verifies:
  1. Field Classification Registry: PUBLIC, PRIVATE, ADMIN_ONLY, SENSITIVE.
  2. Recursive sensitive field stripping (passwords, salts, tokens).
  3. PII masking (email, phone).
  4. Public serializers (certificates, posts, companies).
  5. Multi-role access testing against private endpoints:
     - Anonymous
     - Other intern
     - Mentor
     - Company
     - Admin
"""

import json
import os
import pytest
from app import get_db, row_to_dict
from services.privacy_service import (
    FieldClassification,
    FIELD_CLASSIFICATION_REGISTRY,
    SENSITIVE_KEYS,
    classify_field,
    strip_sensitive_fields,
    mask_email,
    mask_phone,
    filter_fields,
    serialize_public_certificate,
    serialize_public_company,
    serialize_public_post,
)
from tests.conftest import (
    seed_intern,
    seed_company,
    seed_mentor,
    seed_staff,
    login_as_intern,
    login_as_company,
    login_as_mentor,
    login_as_admin,
    logout,
)


class TestFieldClassificationMatrix:
    """Unit tests for the field classification taxonomy, masking, and sanitizer."""

    def test_all_core_models_fields_classified(self):
        for table, fields in FIELD_CLASSIFICATION_REGISTRY.items():
            assert len(fields) > 0, f"Table {table} has no classified fields"
            for field, classification in fields.items():
                assert classification in (
                    FieldClassification.PUBLIC,
                    FieldClassification.PRIVATE,
                    FieldClassification.ADMIN_ONLY,
                    FieldClassification.SENSITIVE,
                ), f"Invalid classification for {table}.{field}: {classification}"

    def test_sensitive_keys_always_classified_as_sensitive(self):
        for key in SENSITIVE_KEYS:
            assert classify_field("intern_accounts", key) == FieldClassification.SENSITIVE
            assert classify_field("companies", key) == FieldClassification.SENSITIVE
            assert classify_field("arbitrary_table", key) == FieldClassification.SENSITIVE

    def test_strip_sensitive_fields_recursive(self):
        payload = {
            "id": 1,
            "name": "Alice",
            "password_hash": "pbkdf2:sha256:secret_hash",
            "salt": "random_salt_123",
            "meta": {
                "token_hash": "token_secret_hash",
                "email": "alice@example.com",
                "nested_list": [
                    {"secret_key": "very_secret", "label": "test"},
                    {"safe": "ok"}
                ]
            }
        }
        cleaned = strip_sensitive_fields(payload)

        assert "password_hash" not in cleaned
        assert "salt" not in cleaned
        assert "token_hash" not in cleaned["meta"]
        assert cleaned["meta"]["email"] == "alice@example.com"
        assert "secret_key" not in cleaned["meta"]["nested_list"][0]
        assert cleaned["meta"]["nested_list"][0]["label"] == "test"
        assert cleaned["meta"]["nested_list"][1]["safe"] == "ok"

    def test_pii_email_masking(self):
        assert mask_email("john.doe@example.com") == "j******e@example.com"
        assert mask_email("a@example.com") == "a*@example.com"
        assert mask_email("ab@example.com") == "a*@example.com"
        assert mask_email("abc@example.com") == "a*c@example.com"
        assert mask_email("") == ""
        assert mask_email(None) == ""
        assert mask_email("invalid-email") == ""

    def test_pii_phone_masking(self):
        assert mask_phone("9876543210") == "******3210"
        assert mask_phone("+919876543210") == "*********3210"
        assert mask_phone("123") == "****"
        assert mask_phone("") == ""
        assert mask_phone(None) == ""


class TestEntitySerializersAndFiltering:
    """Verifies public serializers and role-based field filtering."""

    def test_public_certificate_serializer_strips_pii(self):
        cert_row = {
            "id": 42,
            "intern_id": 999,
            "email": "private_intern@example.com",
            "cert_id": "CERT-2026-ABCDEF",
            "course_title": "AI Agent Development",
            "issued_at": "2026-09-25 12:00:00",
            "tier": "gold",
            "name": "Jane Developer",
        }
        serialized = serialize_public_certificate(cert_row)
        assert serialized["cert_id"] == "CERT-2026-ABCDEF"
        assert serialized["recipient_name"] == "Jane Developer"
        assert serialized["course_title"] == "AI Agent Development"
        assert serialized["issued_at"] == "2026-09-25"
        assert serialized["tier"] == "gold"
        assert "email" not in serialized
        assert "intern_id" not in serialized
        assert "id" not in serialized

    def test_public_company_serializer_strips_credentials_and_private_info(self):
        comp_row = {
            "id": 10,
            "name": "Tech Corp",
            "email": "corp@example.com",
            "phone": "9876543210",
            "website": "https://techcorp.example.com",
            "about": "Innovating software.",
            "password_hash": "pbkdf2:sha256:secret",
            "is_approved": 1,
            "is_active": 1,
        }
        serialized = serialize_public_company(comp_row)
        assert serialized["id"] == 10
        assert serialized["name"] == "Tech Corp"
        assert serialized["website"] == "https://techcorp.example.com"
        assert serialized["about"] == "Innovating software."
        assert "password_hash" not in serialized
        assert "phone" not in serialized
        assert "email" not in serialized
        assert "is_approved" not in serialized

    def test_filter_fields_role_boundaries(self):
        app_row = {
            "id": 100,
            "name": "Bob Applicant",
            "email": "bob@example.com",
            "phone": "9876543210",
            "status": "Applied",
            "admin_note": "Internal review note: strong candidate",
            "mentor_note": "Mentor assessment: pass",
        }
        # Anonymous viewer: receives nothing from private applications
        anon_data = filter_fields("applications", app_row, viewer_role="anonymous", is_owner=False)
        assert anon_data == {}

        # Owning intern: receives personal data, but NOT admin_note or mentor_note
        owner_data = filter_fields("applications", app_row, viewer_role="intern", is_owner=True)
        assert owner_data["name"] == "Bob Applicant"
        assert owner_data["email"] == "bob@example.com"
        assert owner_data["status"] == "Applied"
        assert "admin_note" not in owner_data
        assert "mentor_note" not in owner_data

        # Admin: receives personal data AND admin/mentor notes
        admin_data = filter_fields("applications", app_row, viewer_role="admin", is_owner=False)
        assert admin_data["name"] == "Bob Applicant"
        assert admin_data["admin_note"] == "Internal review note: strong candidate"
        assert admin_data["mentor_note"] == "Mentor assessment: pass"


class TestMultiRolePrivateEndpointEnforcement:
    """
    Master Plan Section 25: Test anonymous, other intern, mentor, company, admin
    against private endpoints.
    """

    def test_intern_me_privacy_matrix(self, app_client):
        client, db_path = app_client
        os.environ["DB_FILE"] = db_path

        # Seed Intern Alice and Intern Bob
        alice_id = seed_intern(db_path, email="alice_priv@example.com", password="AlicePass123!", name="Alice Private")
        bob_id = seed_intern(db_path, email="bob_priv@example.com", password="BobPass123!", name="Bob Private")
        mentor_id = seed_mentor(db_path, email="mentor_priv@example.com", password="MentorPass123!")
        comp_id = seed_company(db_path, email="comp_priv@example.com", password="CompPass123!")

        # 1. Anonymous -> 401
        logout(client)
        resp_anon = client.get("/intern/me")
        assert resp_anon.status_code == 401

        # 2. Company -> 401
        login_as_company(client, db_path, email="comp_priv@example.com", password="CompPass123!")
        resp_comp = client.get("/intern/me")
        assert resp_comp.status_code == 401

        # 3. Mentor -> 401
        login_as_mentor(client, db_path, email="mentor_priv@example.com", password="MentorPass123!")
        resp_mentor = client.get("/intern/me")
        assert resp_mentor.status_code == 401

        # 4. Intern Alice -> 200, receives Alice's info, zero password hash
        login_as_intern(client, db_path, email="alice_priv@example.com", password="AlicePass123!")
        resp_alice = client.get("/intern/me")
        assert resp_alice.status_code == 200
        alice_json = resp_alice.get_json()
        assert alice_json["intern"]["email"] == "alice_priv@example.com"
        assert "password_hash" not in str(resp_alice.data)
        assert "password" not in alice_json["intern"]

        # 5. Intern Bob -> receives Bob's info (cannot view Alice's)
        login_as_intern(client, db_path, email="bob_priv@example.com", password="BobPass123!")
        resp_bob = client.get("/intern/me")
        assert resp_bob.status_code == 200
        bob_json = resp_bob.get_json()
        assert bob_json["intern"]["email"] == "bob_priv@example.com"
        assert "alice_priv" not in str(resp_bob.data)

    def test_company_profile_privacy_matrix(self, app_client):
        client, db_path = app_client
        os.environ["DB_FILE"] = db_path

        seed_company(db_path, email="comp_alpha@example.com", password="AlphaPass123!", name="Alpha Corp")
        seed_intern(db_path, email="intern_eva@example.com", password="EvaPass123!")
        seed_mentor(db_path, email="mentor_eva@example.com", password="MentorPass123!")

        # 1. Anonymous -> blocked (302 redirect to company login or 401)
        logout(client)
        resp_anon = client.get("/company/profile")
        assert resp_anon.status_code in (302, 401)

        # 2. Intern -> blocked
        login_as_intern(client, db_path, email="intern_eva@example.com", password="EvaPass123!")
        resp_intern = client.get("/company/profile")
        assert resp_intern.status_code in (302, 401, 403)

        # 3. Mentor -> blocked
        login_as_mentor(client, db_path, email="mentor_eva@example.com", password="MentorPass123!")
        resp_mentor = client.get("/company/profile")
        assert resp_mentor.status_code in (302, 401, 403)

        # 4. Company Alpha -> 200, zero password_hash in response HTML/data
        login_as_company(client, db_path, email="comp_alpha@example.com", password="AlphaPass123!")
        resp_comp = client.get("/company/profile")
        assert resp_comp.status_code == 200
        assert b"Alpha Corp" in resp_comp.data
        assert b"password_hash" not in resp_comp.data

    def test_company_applicant_list_privacy_matrix(self, app_client):
        client, db_path = app_client
        os.environ["DB_FILE"] = db_path

        comp_a_id = seed_company(db_path, email="company_a@example.com", password="PassA123!", name="Company A")
        comp_b_id = seed_company(db_path, email="company_b@example.com", password="PassB123!", name="Company B")
        intern_id = seed_intern(db_path, email="candidate_c@example.com", password="PassC123!", name="Candidate C")
        mentor_id = seed_mentor(db_path, email="mentor_c@example.com", password="MentorPass123!")

        with get_db() as conn:
            cur = conn.execute("""
                INSERT INTO posts (company_id, post_type, domain, title, slug, description,
                                   responsibilities, skills, location, work_mode, status, created_at)
                VALUES (?, 'job', 'AI Agent Development', 'AI Engineer', 'ai-engineer-101',
                        'Great role with at least 100 characters of high quality description text for testing purposes.',
                        'Building models', 'Python, PyTorch', 'Bengaluru', 'hybrid', 'live', datetime('now'))
            """, (comp_a_id,))
            post_id = cur.lastrowid

            conn.execute("""
                INSERT INTO post_applications (post_id, intern_id, email, comment, status, created_at)
                VALUES (?, ?, 'candidate_c@example.com', 'Super excited to apply!', 'Applied', datetime('now'))
            """, (post_id, intern_id))
            conn.commit()

        # 1. Anonymous -> 401 / redirect
        logout(client)
        resp_anon = client.get(f"/company/posts/{post_id}/applicants")
        assert resp_anon.status_code in (302, 401)

        # 2. Intern -> 401 / 403
        login_as_intern(client, db_path, email="candidate_c@example.com", password="PassC123!")
        resp_intern = client.get(f"/company/posts/{post_id}/applicants")
        assert resp_intern.status_code in (302, 401, 403)

        # 3. Mentor -> 401 / 403
        login_as_mentor(client, db_path, email="mentor_c@example.com", password="MentorPass123!")
        resp_mentor = client.get(f"/company/posts/{post_id}/applicants")
        assert resp_mentor.status_code in (302, 401, 403)

        # 4. Company B (not the owner) -> 403 Forbidden or 404 Not Found (opaque IDOR protection)
        login_as_company(client, db_path, email="company_b@example.com", password="PassB123!")
        resp_comp_b = client.get(f"/company/posts/{post_id}/applicants")
        assert resp_comp_b.status_code in (403, 404)

        # 5. Company A (owner) -> 200, sees applicant, zero password_hash in response
        login_as_company(client, db_path, email="company_a@example.com", password="PassA123!")
        resp_comp_a = client.get(f"/company/posts/{post_id}/applicants")
        assert resp_comp_a.status_code == 200
        assert b"Candidate C" in resp_comp_a.data
        assert b"password_hash" not in resp_comp_a.data

    def test_admin_users_endpoint_privacy_matrix(self, app_client):
        client, db_path = app_client
        os.environ["DB_FILE"] = db_path

        seed_intern(db_path, email="intern_user@example.com", password="InternPass123!")
        seed_company(db_path, email="company_user@example.com", password="CompanyPass123!")
        seed_mentor(db_path, email="mentor_user@example.com", password="MentorPass123!")

        # 1. Anonymous -> 401
        logout(client)
        assert client.get("/admin/users").status_code == 401

        # 2. Intern -> 401
        login_as_intern(client, db_path, email="intern_user@example.com", password="InternPass123!")
        assert client.get("/admin/users").status_code == 401

        # 3. Company -> 401
        login_as_company(client, db_path, email="company_user@example.com", password="CompanyPass123!")
        assert client.get("/admin/users").status_code == 401

        # 4. Mentor -> 401
        login_as_mentor(client, db_path, email="mentor_user@example.com", password="MentorPass123!")
        assert client.get("/admin/users").status_code == 401

        # 5. Admin -> 200, zero password_hash returned anywhere in users JSON
        login_as_admin(client, db_path)
        resp_admin = client.get("/admin/users")
        assert resp_admin.status_code == 200
        admin_data = resp_admin.get_json()
        assert admin_data["status"] == "success"
        assert "password_hash" not in str(resp_admin.data)
        for u in admin_data["users"]:
            assert "password_hash" not in u
            assert "salt" not in u

    def test_public_certificate_endpoint_sanitizes_pii(self, app_client):
        client, db_path = app_client
        os.environ["DB_FILE"] = db_path

        email = "public_cert_intern@example.com"
        intern_id = seed_intern(db_path, email=email, password="CertPass123!", name="Honored Graduate")

        cert_id = "DBERT-CERT-TEST-9999"
        with get_db() as conn:
            conn.execute("""
                INSERT INTO intern_certificates (intern_id, course_id, course_title, cert_id,
                                                 email, issued_at, tier)
                VALUES (?, 1, 'AI Agent Architecture', ?, ?, '2026-09-25 14:00:00', 'gold')
            """, (intern_id, cert_id, email))
            conn.commit()

        # Anonymous public verification
        logout(client)
        resp = client.get(f"/portal/certificate/{cert_id}")
        assert resp.status_code == 200
        assert b"Honored Graduate" in resp.data
        assert b"AI Agent Architecture" in resp.data
        assert b"DBERT-CERT-TEST-9999" in resp.data

        # Critical Privacy Check: intern email and password hashes must NOT be exposed in public HTML
        assert email.encode() not in resp.data
        assert b"password_hash" not in resp.data
        assert b"password" not in resp.data
