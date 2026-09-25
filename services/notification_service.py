"""
services/notification_service.py - Central Notification & Dispatch Domain Service
Fulfills Phase 23 (Monolith Modularization) of INTERNSHIPPORTAL4_LOCAL_AI_AGENT_MASTER_PLAN.md

Encapsulates:
1. High-level notification domain events.
2. Decoupled, transactional dispatching using the event_outbox table.
3. Structured event payloads for async email and message workers.
"""
from typing import Optional, Dict, Any
from services.outbox_service import (
    enqueue_outbox_event,
    EVENT_APPLICATION_SUBMITTED,
    EVENT_APPLICATION_SELECTED,
    EVENT_APPLICATION_REJECTED,
    EVENT_ENROLLMENT_CREATED,
    EVENT_PAYMENT_SUBMITTED,
    EVENT_PAYMENT_ACCEPTED,
    EVENT_PAYMENT_REJECTED,
    EVENT_MENTOR_ASSIGNED,
    EVENT_TASK_ASSIGNED,
    EVENT_TASK_REVIEWED,
    EVENT_CERTIFICATE_ISSUED,
)


class NotificationService:
    """Central notification domain dispatcher."""

    @staticmethod
    def notify_application_submitted(conn, application_id: int, email: str, name: str, domain: str) -> int:
        return enqueue_outbox_event(
            conn=conn,
            event_type=EVENT_APPLICATION_SUBMITTED,
            aggregate_type="application",
            aggregate_id=str(application_id),
            payload={
                "application_id": application_id,
                "email": email,
                "name": name,
                "domain": domain,
                "action": "application_received"
            }
        )

    @staticmethod
    def notify_application_selected(conn, application_id: int, email: str, name: str, domain: str) -> int:
        return enqueue_outbox_event(
            conn=conn,
            event_type=EVENT_APPLICATION_SELECTED,
            aggregate_type="application",
            aggregate_id=str(application_id),
            payload={
                "application_id": application_id,
                "email": email,
                "name": name,
                "domain": domain,
                "action": "candidate_selected"
            }
        )

    @staticmethod
    def notify_application_rejected(conn, application_id: int, email: str, name: str, domain: str) -> int:
        return enqueue_outbox_event(
            conn=conn,
            event_type=EVENT_APPLICATION_REJECTED,
            aggregate_type="application",
            aggregate_id=str(application_id),
            payload={
                "application_id": application_id,
                "email": email,
                "name": name,
                "domain": domain,
                "action": "candidate_rejected"
            }
        )

    @staticmethod
    def notify_enrollment_created(conn, enrollment_id: int, email: str, name: str, course_title: str) -> int:
        return enqueue_outbox_event(
            conn=conn,
            event_type=EVENT_ENROLLMENT_CREATED,
            aggregate_type="enrollment",
            aggregate_id=str(enrollment_id),
            payload={
                "enrollment_id": enrollment_id,
                "email": email,
                "name": name,
                "course_title": course_title,
                "action": "enrollment_confirmed"
            }
        )

    @staticmethod
    def notify_payment_accepted(conn, aggregate_id: str, email: str, amount_inr: int, product: str) -> int:
        return enqueue_outbox_event(
            conn=conn,
            event_type=EVENT_PAYMENT_ACCEPTED,
            aggregate_type="payment",
            aggregate_id=str(aggregate_id),
            payload={
                "email": email,
                "amount_inr": amount_inr,
                "product": product,
                "action": "payment_receipt"
            }
        )

    @staticmethod
    def notify_payment_rejected(conn, aggregate_id: str, email: str, reason: str) -> int:
        return enqueue_outbox_event(
            conn=conn,
            event_type=EVENT_PAYMENT_REJECTED,
            aggregate_type="payment",
            aggregate_id=str(aggregate_id),
            payload={
                "email": email,
                "reason": reason,
                "action": "payment_failure_alert"
            }
        )

    @staticmethod
    def notify_task_reviewed(conn, submission_id: int, email: str, status: str, feedback: str = "") -> int:
        return enqueue_outbox_event(
            conn=conn,
            event_type=EVENT_TASK_REVIEWED,
            aggregate_type="task_submission",
            aggregate_id=str(submission_id),
            payload={
                "submission_id": submission_id,
                "email": email,
                "status": status,
                "feedback": feedback,
                "action": "review_completed"
            }
        )

    @staticmethod
    def notify_certificate_issued(conn, cert_id: str, intern_id: int, email: str, title: str) -> int:
        return enqueue_outbox_event(
            conn=conn,
            event_type=EVENT_CERTIFICATE_ISSUED,
            aggregate_type="certificate",
            aggregate_id=str(cert_id),
            payload={
                "certificate_id": cert_id,
                "intern_id": intern_id,
                "email": email,
                "title": title,
                "action": "certificate_ready"
            }
        )
