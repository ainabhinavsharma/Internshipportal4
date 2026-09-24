"""
services/application_service.py - Application State Machine Service
Implements Phase 6 requirements of INTERNSHIPPORTAL4_LOCAL_AI_AGENT_MASTER_PLAN.md

Provides central validation, role-based authorization, optimistic locking,
and comprehensive audit logging for all application lifecycle transitions.
"""

import json
from datetime import datetime
from typing import Optional, Dict, Any, Tuple, Union

# Application Status Constants (canonical)
STATUS_APPLY_PENDING      = "Apply Pending"
STATUS_UNDER_REVIEW       = "Under Review"
STATUS_ON_HOLD            = "On Hold"
STATUS_SELECTED           = "Selected"
STATUS_ENROLLMENT_PENDING = "Enrollment Pending"
STATUS_ENROLLED           = "Enrolled"
STATUS_ACCEPTED           = "Accepted"
STATUS_REJECTED           = "Rejected"
STATUS_PAID_ENROLLED      = "Paid-Enrolled"
STATUS_PAID_ENROLLED_ALT  = "Paid - Enrolled"

VALID_APPLICATION_STATUSES = {
    STATUS_APPLY_PENDING,
    STATUS_UNDER_REVIEW,
    STATUS_ON_HOLD,
    STATUS_SELECTED,
    STATUS_ENROLLMENT_PENDING,
    STATUS_ENROLLED,
    STATUS_ACCEPTED,
    STATUS_REJECTED,
    STATUS_PAID_ENROLLED,
    STATUS_PAID_ENROLLED_ALT
}

# Permitted state transitions (state machine graph)
VALID_APP_TRANSITIONS: Dict[str, set] = {
    STATUS_APPLY_PENDING:      {STATUS_UNDER_REVIEW, STATUS_REJECTED},
    STATUS_UNDER_REVIEW:       {STATUS_ON_HOLD, STATUS_SELECTED, STATUS_REJECTED},
    STATUS_ON_HOLD:            {STATUS_UNDER_REVIEW, STATUS_SELECTED, STATUS_REJECTED},
    STATUS_SELECTED:           {STATUS_ENROLLMENT_PENDING, STATUS_REJECTED},
    STATUS_ENROLLMENT_PENDING: {STATUS_ENROLLED, STATUS_SELECTED, STATUS_REJECTED, STATUS_PAID_ENROLLED, STATUS_PAID_ENROLLED_ALT},
    STATUS_ENROLLED:           {STATUS_ACCEPTED, STATUS_ENROLLMENT_PENDING, STATUS_REJECTED},
    STATUS_ACCEPTED:           {STATUS_ENROLLED, STATUS_REJECTED},
    STATUS_PAID_ENROLLED:      {STATUS_ACCEPTED, STATUS_REJECTED},
    STATUS_PAID_ENROLLED_ALT:  {STATUS_ACCEPTED, STATUS_REJECTED},
    STATUS_REJECTED:           {STATUS_UNDER_REVIEW},  # Admin can reopen rejected application
}

# Allowed transitions per actor role
INTERN_PERMITTED_TRANSITIONS = {
    (STATUS_APPLY_PENDING, STATUS_UNDER_REVIEW),
    (STATUS_SELECTED, STATUS_ENROLLMENT_PENDING),
}

MENTOR_PERMITTED_TARGETS = {
    STATUS_UNDER_REVIEW,
    STATUS_ON_HOLD,
    STATUS_SELECTED,
    STATUS_REJECTED,
}


class ApplicationStateMachineError(Exception):
    """Base exception for application state machine errors."""
    pass


class ApplicationNotFoundError(ApplicationStateMachineError):
    """Raised when the target application ID does not exist."""
    pass


class InvalidTransitionError(ApplicationStateMachineError):
    """Raised when attempting an illegal transition jump."""
    def __init__(self, current_status: str, target_status: str, message: Optional[str] = None):
        self.current_status = current_status
        self.target_status = target_status
        super().__init__(message or f"Illegal transition from '{current_status}' to '{target_status}'.")


class UnauthorizedTransitionError(ApplicationStateMachineError):
    """Raised when actor does not have permission to execute the transition."""
    pass


class ConcurrentModificationError(ApplicationStateMachineError):
    """Raised when optimistic locking detects a concurrent modification."""
    pass


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def record_status_history(
    conn,
    application_id: int,
    old_status: Optional[str],
    new_status: str,
    changed_by: str,
    reason: Optional[str] = None,
    request_id: Optional[str] = None,
    metadata: Optional[Union[dict, str]] = None
) -> int:
    """Inserts an immutable audit entry into application_status_history."""
    if isinstance(metadata, dict):
        meta_str = json.dumps(metadata)
    else:
        meta_str = str(metadata) if metadata is not None else None

    cur = conn.execute(
        """
        INSERT INTO application_status_history (
            application_id, old_status, new_status,
            changed_by, changed_at, reason, request_id, metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            application_id,
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


def transition_application(
    conn,
    application_id: int,
    target_status: str,
    actor: str,
    actor_role: str = "admin",
    reason: Optional[str] = None,
    request_id: Optional[str] = None,
    metadata: Optional[Union[dict, str]] = None,
    actor_email: Optional[str] = None
) -> Dict[str, Any]:
    """
    Central transition function for applications.
    Validates:
      1. Application exists
      2. Valid target state
      3. Valid transition path from current state
      4. Actor authorization & ownership
      5. Optimistic concurrency (rowcount check)
    Records audit entry in application_status_history.
    
    Returns:
      {
        "success": True,
        "application_id": int,
        "old_status": str,
        "new_status": str,
        "history_id": int,
        "idempotent": bool
      }
    """
    if target_status not in VALID_APPLICATION_STATUSES:
        raise InvalidTransitionError("UNKNOWN", target_status, f"Invalid target status: '{target_status}'.")

    # Fetch current record
    row = conn.execute(
        "SELECT id, email, status, domain, name, rejected_at FROM applications WHERE id = ?",
        (application_id,)
    ).fetchone()

    if not row:
        raise ApplicationNotFoundError(f"Application with ID {application_id} not found.")

    current_status = row["status"]

    # Actor authorization & ownership checks
    actor_role_lower = (actor_role or "").lower()
    if actor_role_lower == "intern":
        # Check ownership: intern must own this application
        if actor_email and row["email"] and row["email"].lower() != actor_email.lower():
            raise UnauthorizedTransitionError("Intern does not own this application record.")
        if (current_status, target_status) not in INTERN_PERMITTED_TRANSITIONS:
            raise UnauthorizedTransitionError(
                f"Interns are not authorized to transition from '{current_status}' to '{target_status}'."
            )
    elif actor_role_lower == "mentor":
        if target_status not in MENTOR_PERMITTED_TARGETS:
            raise UnauthorizedTransitionError(
                f"Mentors cannot transition applications to '{target_status}'."
            )

    # Idempotent no-op check
    if current_status == target_status:
        return {
            "success": True,
            "application_id": application_id,
            "old_status": current_status,
            "new_status": target_status,
            "history_id": None,
            "idempotent": True
        }

    # Validate transition graph
    allowed_targets = VALID_APP_TRANSITIONS.get(current_status, set())
    if target_status not in allowed_targets:
        raise InvalidTransitionError(
            current_status,
            target_status,
            f"Cannot transition application {application_id} from '{current_status}' to '{target_status}'."
        )

    # Admin, system, payment_gateway are permitted for all graph-valid transitions

    # Execute atomic transition with optimistic concurrency check
    now = _now_str()
    rejected_at = now if target_status == STATUS_REJECTED else row["rejected_at"]

    cursor = conn.execute(
        """
        UPDATE applications
        SET status = ?, rejected_at = ?, updated_at = ?
        WHERE id = ? AND status = ?
        """,
        (target_status, rejected_at, now, application_id, current_status)
    )

    if cursor.rowcount == 0:
        raise ConcurrentModificationError(
            f"Application {application_id} status changed concurrently from '{current_status}'."
        )

    # Record history
    history_id = record_status_history(
        conn=conn,
        application_id=application_id,
        old_status=current_status,
        new_status=target_status,
        changed_by=actor,
        reason=reason,
        request_id=request_id,
        metadata=metadata
    )

    return {
        "success": True,
        "application_id": application_id,
        "old_status": current_status,
        "new_status": target_status,
        "history_id": history_id,
        "idempotent": False
    }


def get_application_history(conn, application_id: int):
    """Returns chronological audit history for an application."""
    rows = conn.execute(
        """
        SELECT id, application_id, old_status, new_status,
               changed_by, changed_at, reason, request_id, metadata
        FROM application_status_history
        WHERE application_id = ?
        ORDER BY id ASC
        """,
        (application_id,)
    ).fetchall()
    return [dict(r) for r in rows]
