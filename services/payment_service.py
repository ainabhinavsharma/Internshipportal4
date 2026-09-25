"""
services/payment_service.py - High-Level Payment Domain Service
Fulfills Phase 23 (Monolith Modularization) of INTERNSHIPPORTAL4_LOCAL_AI_AGENT_MASTER_PLAN.md

Encapsulates:
1. Canonical server-side pricing determination for security deposits, paid courses, and hiring fees.
2. Order generation delegating to RazorpayClient.
3. Cryptographic HMAC signature verification & payment idempotency check.
4. Atomically recording payment events into payment_events table.
"""
import os
import time
import json
from services.razorpay_client import (
    create_order as rzp_create_order,
    verify_payment_signature as rzp_verify_sig,
    verify_webhook_signature as rzp_verify_webhook,
    is_razorpay_enabled,
    get_public_config,
    RazorpayError
)

UPI_AMOUNT = int(os.environ.get("UPI_AMOUNT", "1000"))
PAID_PROGRAM_AMOUNT = int(os.environ.get("PAID_PROGRAM_AMOUNT", "1599"))


class PaymentService:
    """Core payment domain service."""

    @staticmethod
    def is_enabled() -> bool:
        return is_razorpay_enabled()

    @staticmethod
    def get_client_config() -> dict:
        return get_public_config()

    @staticmethod
    def determine_pricing(conn, product_type: str, product_id=None, user_id=None, email=None) -> dict:
        """Determines server-side authoritative price and notes dict."""
        product_type = (product_type or "security_deposit").strip()
        ts = int(time.time())

        if product_type == "security_deposit":
            amount_inr = int(os.environ.get("UPI_AMOUNT", str(UPI_AMOUNT)))
            receipt = f"sd_{user_id}_{ts}"
            notes = {"intern_id": user_id, "email": email, "product": "security_deposit"}
        elif product_type == "paid_program":
            amount_inr = int(os.environ.get("PAID_PROGRAM_AMOUNT", str(PAID_PROGRAM_AMOUNT)))
            receipt = f"pp_{user_id}_{ts}"
            notes = {"intern_id": user_id, "email": email, "product": "paid_program"}
        elif product_type == "post_hire_deposit":
            amount_inr = 499
            receipt = f"phd_{user_id}_{ts}"
            notes = {"intern_id": user_id, "email": email, "product": "post_hire_deposit", "post_application_id": product_id}
        elif product_type == "course":
            course = conn.execute("SELECT id, price_inr, title FROM courses WHERE id=?", (product_id,)).fetchone()
            if not course or not course["price_inr"]:
                raise ValueError("Course not found or price not set")
            amount_inr = int(course["price_inr"])
            receipt = f"c_{user_id}_{product_id}_{ts}"
            notes = {"intern_id": user_id, "email": email, "product": "course", "course_id": product_id}
        else:
            raise ValueError(f"Invalid product type: {product_type}")

        return {
            "amount_inr": amount_inr,
            "receipt": receipt,
            "notes": notes,
            "product_type": product_type
        }

    @staticmethod
    def create_payment_order(conn, product_type: str, product_id, user_id: int, email: str) -> dict:
        """Creates an order via Razorpay client with authoritative pricing."""
        pricing = PaymentService.determine_pricing(conn, product_type, product_id, user_id, email)
        order = rzp_create_order(
            amount_inr=pricing["amount_inr"],
            receipt=pricing["receipt"],
            notes=pricing["notes"]
        )
        return {
            "order_id": order["order_id"],
            "amount": order["amount"],
            "currency": order["currency"],
            "key_id": order["key_id"],
            "product_type": pricing["product_type"]
        }

    @staticmethod
    def verify_payment_signature(order_id: str, payment_id: str, signature: str) -> bool:
        """Verifies signature via Razorpay HMAC."""
        return rzp_verify_sig(order_id, payment_id, signature)

    @staticmethod
    def verify_webhook_signature(body: bytes, signature: str) -> bool:
        """Verifies incoming webhook payload signature."""
        return rzp_verify_webhook(body, signature)

    @staticmethod
    def is_payment_processed(conn, payment_id: str) -> bool:
        """Checks if payment_id has already been successfully recorded."""
        if not payment_id:
            return False
        row = conn.execute(
            "SELECT id FROM payment_events WHERE payment_id=? AND status='processed' LIMIT 1",
            (payment_id,)
        ).fetchone()
        return bool(row)

    @staticmethod
    def record_payment_event(conn, event_id: str, event_type: str, order_id: str, payment_id: str, payload: dict, status: str = "processed") -> int:
        """Atomically inserts payment event record."""
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        cursor = conn.execute(
            """
            INSERT OR REPLACE INTO payment_events 
            (event_id, event_type, order_id, payment_id, payload_json, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (event_id, event_type, order_id, payment_id, json.dumps(payload or {}), status, now)
        )
        conn.commit()
        return cursor.lastrowid
