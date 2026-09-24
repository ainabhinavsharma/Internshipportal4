"""
File Security & Upload Sandbox Service
Phase 15: Implements comprehensive file validation, MIME/magic byte inspection,
path traversal defense, UUID-based storage isolation, and object-level download authorization.
"""

import os
import re
import uuid
import mimetypes
from typing import Optional, Dict, Any, Tuple, Union

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "pdf"}
MAX_FILE_SIZE_BYTES = 6 * 1024 * 1024  # 6 MB

# Exact magic byte signatures
MAGIC_SIGNATURES = {
    "png": [b"\x89PNG\r\n\x1a\n"],
    "jpg": [b"\xff\xd8\xff"],
    "pdf": [b"%PDF"],
}

# Malicious signatures to actively reject even if embedded/polyglot
MALICIOUS_PAYLOAD_SIGNATURES = [
    b"<?php",
    b"<?= ",
    b"<script",
    b"<SCRIPT",
    b"<% ",
    b"#!/bin/sh",
    b"#!/bin/bash",
    b"eval(",
    b"system(",
    b"passthru(",
    b"shell_exec(",
]

MIME_TYPE_MAP = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "pdf": "application/pdf",
}


class FileSecurityError(Exception):
    """Base exception for file security violations."""
    pass


class InvalidFileExtensionError(FileSecurityError):
    """Raised when file extension is not in the allowed whitelist."""
    pass


class InvalidFileTypeError(FileSecurityError):
    """Raised when magic bytes do not match allowed formats or contain malicious payloads."""
    pass


class FileTooLargeError(FileSecurityError):
    """Raised when upload size exceeds MAX_FILE_SIZE_BYTES."""
    pass


class PathTraversalError(FileSecurityError):
    """Raised when filename or path contains traversal attempts (e.g., .., separators, null bytes)."""
    pass


class UnauthorizedFileAccessError(FileSecurityError):
    """Raised when user attempts to access a file they do not own or have permission for."""
    pass


def is_allowed_extension(filename: str) -> bool:
    """Verifies that filename has an extension and that the extension is strictly in ALLOWED_EXTENSIONS."""
    if not filename or "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower().strip()
    return ext in ALLOWED_EXTENSIONS


def validate_filename_safety(filename: str) -> str:
    """
    Validates that a filename does not contain path traversal characters,
    directory separators, null bytes, or dangerous sequences.
    Returns the sanitized basename.
    """
    if not filename:
        raise PathTraversalError("Empty filename provided.")

    # Reject null bytes and path separators
    if "\x00" in filename:
        raise PathTraversalError("Null byte detected in filename.")
    if "/" in filename or "\\" in filename:
        raise PathTraversalError("Path separator detected in filename.")
    if ".." in filename:
        raise PathTraversalError("Directory traversal sequence '..' detected in filename.")

    # Remove any leading/trailing spaces or dots
    clean_name = os.path.basename(filename.strip().lstrip("."))
    if not clean_name:
        raise PathTraversalError("Invalid filename structure.")

    return clean_name


def validate_path_within_bounds(base_dir: str, target_filename: str) -> str:
    """
    Resolves the canonical absolute path for base_dir/target_filename
    and guarantees it resides strictly inside base_dir.
    """
    sanitized_name = validate_filename_safety(target_filename)
    abs_base = os.path.abspath(base_dir)
    resolved_path = os.path.abspath(os.path.join(abs_base, sanitized_name))

    # Path must start with base_dir + separator
    if not resolved_path.startswith(abs_base + os.sep) and resolved_path != abs_base:
        raise PathTraversalError(f"Target path '{resolved_path}' escapes base directory '{abs_base}'.")

    return resolved_path


def sniff_magic_type(stream_or_storage) -> Optional[str]:
    """
    Inspects stream header magic bytes (up to 512 bytes) to determine real file type.
    Actively detects polyglot/embedded scripts (PHP, HTML, Bash).
    Rewinds the stream to position 0 afterwards.
    Returns 'png' | 'jpg' | 'pdf' or None.
    """
    stream = getattr(stream_or_storage, "stream", stream_or_storage)
    try:
        header = stream.read(512)
        stream.seek(0)
    except Exception:
        return None

    if not header:
        return None

    # Check for malicious payload fragments anywhere in the header
    for mal_sig in MALICIOUS_PAYLOAD_SIGNATURES:
        if mal_sig in header:
            return None

    # Verify real format by magic bytes
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if header.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if header.startswith(b"%PDF"):
        return "pdf"

    return None


def generate_secure_storage_name(prefix: str, sniffed_type: str) -> str:
    """
    Generates an unpredictable, sanitized UUID filename with canonical extension.
    Example: 'task_12_4_a1b2c3d4e5f6.pdf' or 'screenshot_a1b2c3d4e5f6.png'
    """
    clean_prefix = re.sub(r"[^a-zA-Z0-9_-]", "", prefix).strip("_")
    uid = uuid.uuid4().hex
    ext = "jpg" if sniffed_type in ("jpg", "jpeg") else sniffed_type
    if clean_prefix:
        return f"{clean_prefix}_{uid}.{ext}"
    return f"{uid}.{ext}"


def authorize_file_download(conn, user_context: Optional[Dict[str, Any]], filename: str) -> Tuple[bool, str]:
    """
    Determines whether user_context has legitimate authorization to view/download filename.
    
    Roles & Rules:
    - Anonymous / None: Denied (401)
    - Admin: Allowed for all files (200)
    - Staff: Allowed for all files (200)
    - Intern: Allowed ONLY if the file belongs to them:
        * task_submissions (intern_id or email match)
        * enrollments (email match)
        * course_payments (intern_id match)
        * post_hire_deposits (intern_id match)
    - Company: Allowed if post_hire_deposits or candidate task for their company post
    
    Returns (is_authorized: bool, reason: str)
    """
    if not user_context:
        return False, "login_required"

    role = (user_context.get("role") or "").lower()
    is_admin = bool(user_context.get("is_admin") or role in ("admin", "superadmin"))
    is_staff = bool(user_context.get("is_staff") or role == "staff")

    if is_admin or is_staff:
        return True, "authorized_staff_or_admin"

    clean_file = os.path.basename(filename)

    if role == "intern":
        intern_id = user_context.get("id") or user_context.get("user_id") or user_context.get("intern_id")
        email = (user_context.get("email") or "").lower().strip()

        # 1. Check task submissions
        row_sub = conn.execute("""
            SELECT id FROM task_submissions
            WHERE (intern_id = ? OR (email IS NOT NULL AND LOWER(email) = ?))
              AND (submission_file = ? OR submission_file LIKE ?)
            LIMIT 1
        """, (intern_id, email, clean_file, f"%/{clean_file}")).fetchone()
        if row_sub:
            return True, "task_submission_owner"

        # 2. Check enrollments
        row_enr = conn.execute("""
            SELECT id FROM enrollments
            WHERE ((intern_id IS NOT NULL AND intern_id = ?) OR (email IS NOT NULL AND LOWER(email) = ?))
              AND (payment_screenshot = ? OR payment_screenshot LIKE ?)
            LIMIT 1
        """, (intern_id, email, clean_file, f"%/{clean_file}")).fetchone()
        if row_enr:
            return True, "enrollment_screenshot_owner"

        # 3. Check course payments
        row_cp = conn.execute("""
            SELECT id FROM course_payments
            WHERE (intern_id = ? OR intern_id IN (SELECT id FROM intern_accounts WHERE LOWER(email) = ?))
              AND (payment_screenshot = ? OR payment_screenshot LIKE ?)
            LIMIT 1
        """, (intern_id, email, clean_file, f"%/{clean_file}")).fetchone()
        if row_cp:
            return True, "course_payment_owner"

        # 4. Check post-hire deposits
        row_dep = conn.execute("""
            SELECT id FROM post_hire_deposits
            WHERE (intern_id = ? OR intern_id IN (SELECT id FROM intern_accounts WHERE LOWER(email) = ?))
              AND (payment_screenshot = ? OR payment_screenshot LIKE ?)
            LIMIT 1
        """, (intern_id, email, clean_file, f"%/{clean_file}")).fetchone()
        if row_dep:
            return True, "post_hire_deposit_owner"

        return False, "forbidden_not_owner"

    if role == "company":
        company_id = user_context.get("id") or user_context.get("company_id")
        row_comp_dep = conn.execute("""
            SELECT d.id FROM post_hire_deposits d
            JOIN posts p ON d.post_id = p.id
            WHERE p.company_id = ? AND (d.payment_screenshot = ? OR d.payment_screenshot LIKE ?)
            LIMIT 1
        """, (company_id, clean_file, f"%/{clean_file}")).fetchone()
        if row_comp_dep:
            return True, "company_post_deposit"
        return False, "forbidden_company_not_owner"

    if role == "mentor":
        # Mentors can view task submissions
        return True, "mentor_review_authorized"

    return False, "forbidden_role"
