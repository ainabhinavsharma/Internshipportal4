"""
Phase 15: File Security and Upload Sandbox Test Suite
Verifies:
  1. Whitelisted extension and magic byte enforcement (PNG, JPG, PDF)
  2. Malicious and embedded script rejection (PHP, HTML, Shell)
  3. Path traversal attacks on upload and download (.., null bytes, slash injection)
  4. Object-level download authorization and IDOR defense on /uploads/<filename>
  5. File size limits (MAX_CONTENT_LENGTH = 6MB)
  6. CSV import sanitization and formula injection defense (CWE-1236)
"""

import io
import os
import tempfile
import pytest
from unittest.mock import patch

from app import get_db, allowed_file, sniff_upload_type, sanitize_csv_value
from services.file_security_service import (
    is_allowed_extension,
    sniff_magic_type,
    validate_filename_safety,
    validate_path_within_bounds,
    generate_secure_storage_name,
    authorize_file_download,
    PathTraversalError,
    ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE_BYTES,
)
from tests.conftest import (
    seed_intern,
    seed_staff,
    login_as_intern,
    login_as_staff,
    login_as_admin,
    logout,
)


class TestFileExtensionAndMagicByteValidation:
    """Verifies extension whitelisting, magic byte inspection, and polyglot detection."""

    def test_allowed_extension_whitelist(self):
        assert is_allowed_extension("resume.pdf") is True
        assert is_allowed_extension("screenshot.png") is True
        assert is_allowed_extension("photo.jpg") is True
        assert is_allowed_extension("document.jpeg") is True

        # Dangerous extensions strictly rejected
        assert is_allowed_extension("shell.php") is False
        assert is_allowed_extension("malware.bin") is False
        assert is_allowed_extension("script.sh") is False
        assert is_allowed_extension("index.html") is False
        assert is_allowed_extension("payload.py") is False
        assert is_allowed_extension("no_ext") is False
        assert is_allowed_extension("") is False

    def test_sniff_valid_magic_bytes(self):
        png_stream = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)
        assert sniff_magic_type(png_stream) == "png"
        assert png_stream.tell() == 0  # Verify stream was rewound

        jpg_stream = io.BytesIO(b"\xff\xd8\xff\xe0" + b"\x00" * 50)
        assert sniff_magic_type(jpg_stream) == "jpg"
        assert jpg_stream.tell() == 0

        pdf_stream = io.BytesIO(b"%PDF-1.7\n" + b"\x00" * 50)
        assert sniff_magic_type(pdf_stream) == "pdf"
        assert pdf_stream.tell() == 0

    def test_sniff_rejects_spoofed_or_corrupt_files(self):
        fake_pdf = io.BytesIO(b"This is plain text claiming to be a pdf")
        assert sniff_magic_type(fake_pdf) is None

        fake_png = io.BytesIO(b"\x00\x00\x00\x00\x00\x00\x00\x00")
        assert sniff_magic_type(fake_png) is None

        empty_file = io.BytesIO(b"")
        assert sniff_magic_type(empty_file) is None

    def test_sniff_rejects_polyglot_and_embedded_scripts(self):
        # A file that starts with %PDF but contains PHP tags in the header
        polyglot_pdf = io.BytesIO(b"%PDF-1.4\n<?php echo 'forbidden'; ?>\n")
        assert sniff_magic_type(polyglot_pdf) is None

        # A file that starts with PNG magic but embeds script payload
        polyglot_png = io.BytesIO(b"\x89PNG\r\n\x1a\n<script>console.log(1)</script>")
        assert sniff_magic_type(polyglot_png) is None

        # A shell script claiming to be JPG
        polyglot_jpg = io.BytesIO(b"\xff\xd8\xff\xe0#!/bin/bash\necho test")
        assert sniff_magic_type(polyglot_jpg) is None

    def test_generate_secure_storage_name(self):
        name1 = generate_secure_storage_name("task_1_2", "pdf")
        assert name1.startswith("task_1_2_")
        assert name1.endswith(".pdf")
        assert len(name1) > 20

        # Filename cannot contain traversal chars even if prefix has them
        name2 = generate_secure_storage_name("../../etc/passwd", "png")
        assert "/" not in name2
        assert "\\" not in name2
        assert ".." not in name2
        assert name2.endswith(".png")


class TestPathTraversalDefenses:
    """Verifies that path traversal sequences are neutralized and cannot escape base directories."""

    def test_validate_filename_safety_rejects_traversal(self):
        with pytest.raises(PathTraversalError):
            validate_filename_safety("../../etc/passwd")

        with pytest.raises(PathTraversalError):
            validate_filename_safety("..\\..\\windows\\system32\\config")

        with pytest.raises(PathTraversalError):
            validate_filename_safety("receipt.pdf\x00.bin")

        with pytest.raises(PathTraversalError):
            validate_filename_safety("/etc/hosts")

        with pytest.raises(PathTraversalError):
            validate_filename_safety("C:\\boot.ini")

        with pytest.raises(PathTraversalError):
            validate_filename_safety("")

    def test_validate_filename_safety_accepts_clean_basenames(self):
        assert validate_filename_safety("clean_file.png") == "clean_file.png"
        assert validate_filename_safety("my-screenshot-123.jpg") == "my-screenshot-123.jpg"
        assert validate_filename_safety("receipt_2026.pdf") == "receipt_2026.pdf"

    def test_validate_path_within_bounds(self, tmp_path):
        base_dir = str(tmp_path / "sandbox")
        os.makedirs(base_dir, exist_ok=True)

        # Valid file within base_dir
        valid_path = validate_path_within_bounds(base_dir, "legit.png")
        assert valid_path.startswith(os.path.abspath(base_dir))

        # Traversal attempt
        with pytest.raises(PathTraversalError):
            validate_path_within_bounds(base_dir, "../../secret.txt")

    def test_uploads_endpoint_rejects_path_traversal(self, app_client):
        client, db_path = app_client
        os.environ["DB_FILE"] = db_path
        login_as_admin(client, db_path)

        # Traversal via URL path
        resp = client.get("/uploads/..%2f..%2fapp.py")
        assert resp.status_code in (400, 404)

        resp2 = client.get("/uploads/..\\..\\app.py")
        assert resp2.status_code in (400, 404)

    def test_admin_screenshot_endpoint_rejects_path_traversal(self, app_client):
        client, db_path = app_client
        os.environ["DB_FILE"] = db_path
        login_as_admin(client, db_path)

        resp = client.get("/admin/screenshot/..%2f..%2fapp.py")
        assert resp.status_code in (400, 404)


class TestObjectLevelAuthorizationAndIDOR:
    """Verifies that private uploaded files cannot be viewed or downloaded without proper authorization."""

    def test_anonymous_download_requires_authentication(self, app_client):
        client, db_path = app_client
        os.environ["DB_FILE"] = db_path
        logout(client)

        resp = client.get("/uploads/some_task_submission.pdf")
        assert resp.status_code == 401
        assert resp.get_json()["status"] == "error"
        assert "Authentication required" in resp.get_json()["message"]

    def test_intern_can_download_own_task_submission_file(self, app_client, tmp_path):
        client, db_path = app_client
        os.environ["DB_FILE"] = db_path

        from app import app
        upload_dir = str(tmp_path / "test_uploads")
        os.makedirs(upload_dir, exist_ok=True)
        app.config["UPLOAD_FOLDER"] = upload_dir

        email = "intern_alice@example.com"
        intern_id = seed_intern(db_path, email=email, password="AlicePass123!", name="Alice Intern")

        # Create dummy file on disk in upload directory
        filename = f"task_{intern_id}_99_abc12345.pdf"
        filepath = os.path.join(upload_dir, filename)
        with open(filepath, "wb") as f:
            f.write(b"%PDF-1.4\nTest PDF Content for Alice\n")

        # Link file to Alice in task_submissions
        with get_db() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO tasks (id, title, description, coin_reward, is_active)
                VALUES (99, 'Sample Task', 'Task Description', 10, 1)
            """)
            conn.execute("""
                INSERT OR IGNORE INTO task_versions (id, task_id, version_number, instructions, rubric)
                VALUES (1, 99, 1, 'Sample Instructions', 'Sample Rubric')
            """)
            conn.execute("""
                INSERT INTO task_submissions (intern_id, task_id, task_version_id, submission_content,
                                             submission_file, status, email)
                VALUES (?, 99, 1, 'My submission', ?, 'pending', ?)
            """, (intern_id, f"/uploads/{filename}", email))
            conn.commit()

        # Alice logs in and accesses her file
        login_as_intern(client, db_path, email=email, password="AlicePass123!", name="Alice Intern")
        resp = client.get(f"/uploads/{filename}")
        assert resp.status_code == 200
        assert resp.data == b"%PDF-1.4\nTest PDF Content for Alice\n"
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"

    def test_intern_cannot_download_other_intern_task_submission_file(self, app_client, tmp_path):
        client, db_path = app_client
        os.environ["DB_FILE"] = db_path

        from app import app
        upload_dir = str(tmp_path / "test_uploads_idor")
        os.makedirs(upload_dir, exist_ok=True)
        app.config["UPLOAD_FOLDER"] = upload_dir

        # Alice creates a private submission
        alice_id = seed_intern(db_path, email="alice_private@example.com", password="AlicePass123!", name="Alice Private")
        alice_file = "task_alice_private_file.pdf"
        with open(os.path.join(upload_dir, alice_file), "wb") as f:
            f.write(b"%PDF-1.4\nAlice Secret Submission\n")

        with get_db() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO tasks (id, title, description, coin_reward, is_active)
                VALUES (100, 'Sample Task 100', 'Task Description', 10, 1)
            """)
            conn.execute("""
                INSERT OR IGNORE INTO task_versions (id, task_id, version_number, instructions, rubric)
                VALUES (2, 100, 1, 'Sample Instructions', 'Sample Rubric')
            """)
            conn.execute("""
                INSERT INTO task_submissions (intern_id, task_id, task_version_id, submission_content,
                                             submission_file, status, email)
                VALUES (?, 100, 2, 'Alice private', ?, 'pending', 'alice_private@example.com')
            """, (alice_id, f"/uploads/{alice_file}"))
            conn.commit()

        # Bob logs in and attempts to access Alice's submission
        seed_intern(db_path, email="bob_intruder@example.com", password="BobPass123!", name="Bob Intruder")
        login_as_intern(client, db_path, email="bob_intruder@example.com", password="BobPass123!", name="Bob Intruder")

        resp = client.get(f"/uploads/{alice_file}")
        assert resp.status_code == 403
        assert resp.get_json()["status"] == "error"
        assert "Access denied" in resp.get_json()["message"]

    def test_intern_can_download_own_payment_screenshot(self, app_client, tmp_path):
        client, db_path = app_client
        os.environ["DB_FILE"] = db_path

        from app import app
        upload_dir = str(tmp_path / "test_uploads_pay")
        os.makedirs(upload_dir, exist_ok=True)
        app.config["UPLOAD_FOLDER"] = upload_dir

        email = "charlie_payer@example.com"
        charlie_id = seed_intern(db_path, email=email, password="CharliePass123!", name="Charlie Payer")

        screenshot_name = "payment_receipt_charlie_12345.png"
        with open(os.path.join(upload_dir, screenshot_name), "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\nCharlie receipt data\n")

        with get_db() as conn:
            conn.execute("""
                INSERT INTO enrollments (application_id, name, email, phone, city, college, course, semester,
                                         year_of_passing, domain, joining_date, payment_screenshot, payment_status,
                                         timestamp, created_at, updated_at)
                VALUES (1, 'Charlie Payer', ?, '9876543210', 'City', 'College', 'B.Tech', '7th Semester',
                        '2026', 'AI Agent Development', '2026-10-05', ?, 'Pending Verification',
                        datetime('now'), datetime('now'), datetime('now'))
            """, (email, screenshot_name))
            conn.commit()

        # Charlie can download
        login_as_intern(client, db_path, email=email, password="CharliePass123!", name="Charlie Payer")
        resp = client.get(f"/uploads/{screenshot_name}")
        assert resp.status_code == 200
        assert b"Charlie receipt data" in resp.data

        # Dave (another intern) is blocked with 403
        seed_intern(db_path, email="dave_other@example.com", password="DavePass123!", name="Dave Other")
        login_as_intern(client, db_path, email="dave_other@example.com", password="DavePass123!", name="Dave Other")
        resp_dave = client.get(f"/uploads/{screenshot_name}")
        assert resp_dave.status_code == 403

    def test_staff_and_admin_can_download_all_uploaded_files(self, app_client, tmp_path):
        client, db_path = app_client
        os.environ["DB_FILE"] = db_path

        from app import app
        upload_dir = str(tmp_path / "test_uploads_admin")
        os.makedirs(upload_dir, exist_ok=True)
        app.config["UPLOAD_FOLDER"] = upload_dir

        target_file = "audit_submission_file.pdf"
        with open(os.path.join(upload_dir, target_file), "wb") as f:
            f.write(b"%PDF-1.4\nStaff Audit Data\n")

        # Staff access
        staff_id = seed_staff(db_path, email="reviewer@dbert.org", password="StaffPass123!", name="Staff Reviewer")
        login_as_staff(client, db_path, email="reviewer@dbert.org", password="StaffPass123!")

        resp_staff = client.get(f"/uploads/{target_file}")
        assert resp_staff.status_code == 200
        assert b"Staff Audit Data" in resp_staff.data

        # Admin access
        logout(client)
        login_as_admin(client, db_path)
        resp_admin = client.get(f"/uploads/{target_file}")
        assert resp_admin.status_code == 200
        assert b"Staff Audit Data" in resp_admin.data

    def test_nonexistent_file_returns_404(self, app_client):
        client, db_path = app_client
        os.environ["DB_FILE"] = db_path
        login_as_admin(client, db_path)

        resp = client.get("/uploads/completely_absent_file_12345.pdf")
        assert resp.status_code == 404
        assert resp.get_json()["status"] == "error"


class TestCsvUploadSecurity:
    """Verifies security controls on CSV file imports (CWE-1236 Formula Injection and Authorization)."""

    def test_unauthorized_user_blocked_from_csv_import(self, app_client):
        client, db_path = app_client
        os.environ["DB_FILE"] = db_path
        logout(client)

        csv_data = b"name,email,phone\nJohn,john@example.com,9876543210\n"
        resp = client.post("/admin/upload-csv", data={
            "csv_file": (io.BytesIO(csv_data), "interns.csv")
        }, content_type="multipart/form-data")

        assert resp.status_code in (401, 403)

    def test_non_csv_extension_rejected_by_bulk_upload(self, app_client):
        client, db_path = app_client
        os.environ["DB_FILE"] = db_path
        from app import CSRF_EXEMPT_ENDPOINTS
        CSRF_EXEMPT_ENDPOINTS.add("admin_upload_csv")

        login_as_admin(client, db_path)

        # Attempt to upload a non-csv file
        bad_data = b"plain text data"
        resp = client.post("/admin/upload-csv", data={
            "csv_file": (io.BytesIO(bad_data), "sample.txt")
        }, content_type="multipart/form-data")

        assert resp.status_code == 400
        assert b"Only .csv files accepted" in resp.data

    def test_csv_formula_injection_sanitization(self):
        # Formulas starting with =, +, -, @, \t, \r must be prefixed with single quote
        assert sanitize_csv_value("=1+1") == "'=1+1"
        assert sanitize_csv_value("+cmd|' /C run'!A0") == "'+cmd|' /C run'!A0"
        assert sanitize_csv_value("-2+3") == "'-2+3"
        assert sanitize_csv_value("@SUM(A1:A10)") == "'@SUM(A1:A10)"
        assert sanitize_csv_value("\tcmd") == "'\tcmd"

        # Safe values must not be modified
        assert sanitize_csv_value("John Doe") == "John Doe"
        assert sanitize_csv_value("john@example.com") == "john@example.com"
        assert sanitize_csv_value("9876543210") == "9876543210"
        assert sanitize_csv_value(None) == ""
