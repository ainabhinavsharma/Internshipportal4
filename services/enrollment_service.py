"""
services/enrollment_service.py - Enrollment State Machine Service
Implements Phase 7 requirements of INTERNSHIPPORTAL4_LOCAL_AI_AGENT_MASTER_PLAN.md

Separates Application status from Enrollment status, manages lifecycle transitions,
enforces role-based permissions, prevents impossible state combinations, and synchronizes
with the Application State Machine.
"""

import json
from datetime import datetime
from typing import Optional, Dict, Any, Union

from services.application_service import (
    transition_application,
    ApplicationStateMachineError,
    STATUS_ACCEPTED,
    STATUS_ENROLLMENT_PENDING,
    STATUS_PAID_ENROLLED,
    STATUS_ENROLLED
)

# Canonical Enrollment Payment Status Constants
ENROLLMENT_STATUS_PENDING  = "Pending Verification"
ENROLLMENT_STATUS_ACCEPTED = "Accepted"
ENROLLMENT_STATUS_REJECTED = "Rejected"
ENROLLMENT_STATUS_REFUNDED = "Refunded"

VALID_ENROLLMENT_STATUSES = {
    ENROLLMENT_STATUS_PENDING,
    ENROLLMENT_STATUS_ACCEPTED,
    ENROLLMENT_STATUS_REJECTED,
    ENROLLMENT_STATUS_REFUNDED,
}

# Permitted state transitions graph
VALID_ENROLLMENT_TRANSITIONS = {
    ENROLLMENT_STATUS_PENDING:  {ENROLLMENT_STATUS_ACCEPTED, ENROLLMENT_STATUS_REJECTED},
    ENROLLMENT_STATUS_REJECTED: {ENROLLMENT_STATUS_PENDING},   # Re-upload receipt / re-verify
    ENROLLMENT_STATUS_ACCEPTED: {ENROLLMENT_STATUS_REJECTED, ENROLLMENT_STATUS_REFUNDED},
    ENROLLMENT_STATUS_REFUNDED: set(),                         # Terminal state
}

# Permissions by actor role
ADMIN_ALLOWED_TARGETS = {
    ENROLLMENT_STATUS_ACCEPTED,
    ENROLLMENT_STATUS_REJECTED,
    ENROLLMENT_STATUS_REFUNDED,
    ENROLLMENT_STATUS_PENDING,
}

SYSTEM_ALLOWED_TARGETS = {
    ENROLLMENT_STATUS_ACCEPTED,
    ENROLLMENT_STATUS_PENDING,
}


class EnrollmentStateMachineError(Exception):
    """Base exception for enrollment state machine errors."""
    pass


class EnrollmentNotFoundError(EnrollmentStateMachineError):
    """Raised when the target enrollment ID does not exist."""
    pass


class InvalidEnrollmentTransitionError(EnrollmentStateMachineError):
    """Raised when attempting an illegal enrollment transition jump."""
    def __init__(self, current_status: str, target_status: str, message: Optional[str] = None):
        self.current_status = current_status
        self.target_status = target_status
        super().__init__(message or f"Illegal enrollment transition from '{current_status}' to '{target_status}'.")


class UnauthorizedEnrollmentError(EnrollmentStateMachineError):
    """Raised when actor lacks permission to transition the enrollment."""
    pass


class ConcurrentEnrollmentModificationError(EnrollmentStateMachineError):
    """Raised when optimistic locking detects a concurrent modification."""
    pass


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def record_enrollment_history(
    conn,
    enrollment_id: int,
    old_status: Optional[str],
    new_status: str,
    changed_by: str,
    reason: Optional[str] = None,
    request_id: Optional[str] = None,
    metadata: Optional[Union[dict, str]] = None
) -> int:
    """Inserts an immutable audit entry into enrollment_status_history."""
    if isinstance(metadata, dict):
        meta_str = json.dumps(metadata)
    else:
        meta_str = str(metadata) if metadata is not None else None

    cur = conn.execute(
        """
        INSERT INTO enrollment_status_history (
            enrollment_id, old_status, new_status,
            changed_by, changed_at, reason, request_id, metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            enrollment_id,
            old_status,
            new_status,
            changed_by,
            _now_str(),
            reason or "",
            request_id or "",
            meta_str
        )
    )
    return cur.lastrowid


def transition_enrollment(
    conn,
    enrollment_id: int,
    target_status: str,
    actor: str,
    actor_role: str = "admin",
    reason: Optional[str] = None,
    request_id: Optional[str] = None,
    metadata: Optional[Union[dict, str]] = None,
    sync_application: bool = True,
    expected_status: Optional[str] = None
) -> Dict[str, Any]:
    """
    Central transition function for enrollments.
    Validates:
      1. Enrollment exists
      2. Valid target state
      3. Actor authorization
      4. Stale request / concurrency check (expected_status)
      5. Valid transition graph
      6. Optimistic concurrency control
    Optionally synchronizes matching application status.
    """
    if target_status not in VALID_ENROLLMENT_STATUSES:
        raise InvalidEnrollmentTransitionError("UNKNOWN", target_status, f"Invalid target status: '{target_status}'.")

    # Fetch current enrollment
    row = conn.execute(
        "SELECT id, application_id, email, domain, payment_status, product FROM enrollments WHERE id = ?",
        (enrollment_id,)
    ).fetchone()

    if not row:
        raise EnrollmentNotFoundError(f"Enrollment with ID {enrollment_id} not found.")

    current_status = row["payment_status"]

    # Concurrency / stale UI check
    if expected_status and current_status != expected_status:
        raise ConcurrentEnrollmentModificationError(
            f"Enrollment {enrollment_id} status changed concurrently from '{expected_status}' to '{current_status}'."
        )

    # Role validation
    role_lower = (actor_role or "").lower()
    if role_lower == "intern":
        # Interns can only submit receipt (moving from Rejected back to Pending Verification)
        if target_status != ENROLLMENT_STATUS_PENDING:
            raise UnauthorizedEnrollmentError(
                f"Interns are not authorized to set enrollment status to '{target_status}'."
            )
    elif role_lower == "mentor":
        raise UnauthorizedEnrollmentError("Mentors do not have financial enrollment review permissions.")
    elif role_lower not in ("admin", "system", "payment_gateway"):
        raise UnauthorizedEnrollmentError(f"Role '{actor_role}' is not authorized to transition enrollments.")

    # Idempotent no-op
    if current_status == target_status:
        return {
            "success": True,
            "enrollment_id": enrollment_id,
            "old_status": current_status,
            "new_status": target_status,
            "history_id": None,
            "idempotent": True
        }

    # Validate transition graph
    allowed = VALID_ENROLLMENT_TRANSITIONS.get(current_status, set())
    if target_status not in allowed:
        raise InvalidEnrollmentTransitionError(
            current_status,
            target_status,
            f"Cannot transition enrollment {enrollment_id} from '{current_status}' to '{target_status}'."
        )

    # Atomic update with optimistic concurrency
    now = _now_str()
    cur = conn.execute(
        """
        UPDATE enrollments
        SET payment_status = ?, admin_note = COALESCE(?, admin_note), updated_at = ?
        WHERE id = ? AND payment_status = ?
        """,
        (target_status, reason, now, enrollment_id, current_status)
    )

    if cur.rowcount == 0:
        raise ConcurrentEnrollmentModificationError(
            f"Enrollment {enrollment_id} was modified concurrently."
        )

    # Record history
    history_id = record_enrollment_history(
        conn=conn,
        enrollment_id=enrollment_id,
        old_status=current_status,
        new_status=target_status,
        changed_by=actor,
        reason=reason,
        request_id=request_id,
        metadata=metadata
    )

    # Synchronize application status if requested
    synced_app_id = None
    if sync_application:
        email = row["email"]
        domain = row["domain"]
        app_row = None
        if row["application_id"]:
            app_row = conn.execute("SELECT id, status FROM applications WHERE id = ?", (row["application_id"],)).fetchone()
        if not app_row and email:
            app_row = conn.execute(
                "SELECT id, status FROM applications WHERE LOWER(email) = ? AND (domain = ? OR ? IS NULL) ORDER BY id DESC LIMIT 1",
                (email.lower(), domain, domain)
            ).fetchone()

        if app_row:
            synced_app_id = app_row["id"]
            if target_status == ENROLLMENT_STATUS_ACCEPTED:
                target_app_status = STATUS_PAID_ENROLLED if row["product"] == "paid_program" else STATUS_ACCEPTED
                try:
                    transition_application(
                        conn=conn,
                        application_id=app_row["id"],
                        target_status=target_app_status,
                        actor=actor,
                        actor_role=actor_role,
                        reason=f"Enrollment {enrollment_id} accepted: {reason or ''}".strip(),
                        request_id=request_id
                    )
                except ApplicationStateMachineError:
                    # In case of non-critical transition skip, proceed safely
                    pass
            elif target_status == ENROLLMENT_STATUS_REJECTED:
                # Revert back to Enrollment Pending
                try:
                    transition_application(
                        conn=conn,
                        application_id=app_row["id"],
                        target_status=STATUS_ENROLLMENT_PENDING,
                        actor=actor,
                        actor_role=actor_role,
                        reason=f"Enrollment {enrollment_id} rejected: {reason or ''}".strip(),
                        request_id=request_id
                    )
                except ApplicationStateMachineError:
                    pass

    return {
        "success": True,
        "enrollment_id": enrollment_id,
        "old_status": current_status,
        "new_status": target_status,
        "history_id": history_id,
        "synced_application_id": synced_app_id,
        "idempotent": False
    }


def get_enrollment_history(conn, enrollment_id: int):
    """Returns chronological audit history for an enrollment."""
    rows = conn.execute(
        """
        SELECT id, enrollment_id, old_status, new_status,
               changed_by, changed_at, reason, request_id, metadata
        FROM enrollment_status_history
        WHERE enrollment_id = ?
        ORDER BY id ASC
        """,
        (enrollment_id,)
    ).fetchall()
    return [dict(r) for r in rows]
