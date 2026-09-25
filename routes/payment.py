"""
routes/payment.py - Payment Gateway & Verification Routing Blueprint
Fulfills Phase 23 (Monolith Modularization) of INTERNSHIPPORTAL4_LOCAL_AI_AGENT_MASTER_PLAN.md

Endpoints:
- POST /api/payment/razorpay/create-order
- POST /api/payment/razorpay/verify-payment
- POST /api/payment/razorpay/webhook
- GET  /api/payment/status
"""
import uuid
import time
from flask import Blueprint, jsonify, request
from services.payment_service import PaymentService
from services.auth_service import AuthService
from app import (
    get_db, clean_text, get_client_ip, log_abuse, log_error, log_info,
    now_str, make_batch_label, send_enrollment_confirmation_email,
    transition_application, STATUS_ENROLLED, ApplicationStateMachineError,
    UPI_AMOUNT, PAID_PROGRAM_AMOUNT, razorpay_client
)

payment_bp = Blueprint("payment", __name__)


@payment_bp.route("/api/payment/status", methods=["GET"])
def api_payment_status():
    """Returns payment gateway operational configuration status."""
    return jsonify({
        "status": "success",
        "gateway_enabled": PaymentService.is_enabled(),
        "config": PaymentService.get_client_config()
    })


@payment_bp.route("/api/payment/razorpay/create-order", methods=["POST"])
def api_razorpay_create_order():
    """Server-side order creation for Razorpay with authoritative server pricing."""
    try:
        if not PaymentService.is_enabled():
            return jsonify({
                "status": "error",
                "message": "Razorpay online payments are currently unavailable. Please use the UPI QR code fallback."
            }), 503

        with get_db() as conn:
            user = AuthService.require_role(conn, "intern")
        if not user:
            return jsonify({"status": "error", "message": "Unauthorized"}), 401

        data = request.get_json(silent=True) or {}
        product_type = clean_text(data.get("product_type", "security_deposit"))
        product_id = data.get("product_id")

        with get_db() as conn:
            order_data = PaymentService.create_payment_order(
                conn=conn,
                product_type=product_type,
                product_id=product_id,
                user_id=user["id"],
                email=user["email"]
            )

        return jsonify({
            "status": "success",
            "order_id": order_data["order_id"],
            "amount": order_data["amount"],
            "currency": order_data["currency"],
            "key_id": order_data["key_id"],
            "product_type": order_data["product_type"]
        })
    except Exception as e:
        log_error("razorpay_create_order", e)
        return jsonify({"status": "error", "message": str(e)}), 500


@payment_bp.route("/api/payment/razorpay/verify-payment", methods=["POST"])
def api_razorpay_verify_payment():
    """Verifies HMAC signature of Razorpay payment and atomically completes business transition."""
    try:
        with get_db() as conn:
            user = AuthService.require_role(conn, "intern")
        if not user:
            return jsonify({"status": "error", "message": "Unauthorized"}), 401

        data = request.get_json(silent=True) or {}
        order_id = clean_text(data.get("razorpay_order_id"))
        payment_id = clean_text(data.get("razorpay_payment_id"))
        signature = clean_text(data.get("razorpay_signature"))
        product_type = clean_text(data.get("product_type", "security_deposit"))
        joining_date = clean_text(data.get("joining_date"))
        domain = clean_text(data.get("domain"))
        req_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

        if not (order_id and payment_id and signature):
            return jsonify({"status": "error", "message": "Missing payment verification parameters"}), 400

        is_valid = PaymentService.verify_payment_signature(order_id, payment_id, signature)
        if not is_valid:
            log_abuse(get_client_ip(), "/api/payment/razorpay/verify-payment", f"sig_mismatch:{payment_id}", "invalid_signature", user["email"])
            return jsonify({"status": "error", "message": "Payment verification failed: invalid signature"}), 400

        email = user["email"]
        with get_db() as conn:
            if PaymentService.is_payment_processed(conn, payment_id):
                return jsonify({"status": "success", "message": "Payment already processed.", "redirect": "/portal"})

            acct = conn.execute("SELECT * FROM intern_accounts WHERE email=? LIMIT 1", (email,)).fetchone()
            if not acct:
                return jsonify({"status": "error", "message": "Intern account not found."}), 404

            app_row = conn.execute("SELECT * FROM applications WHERE LOWER(email)=? ORDER BY id DESC LIMIT 1", (email,)).fetchone()
            now = now_str()

            if product_type == "security_deposit":
                batch_label = make_batch_label(joining_date) if joining_date else ""
                domain_to_save = domain or (app_row["domain"] if app_row else "")
                conn.execute(
                    """
                    INSERT INTO enrollments (
                        application_id, timestamp, name, email, phone, city, college,
                        course, semester, year_of_passing, domain, joining_date,
                        batch_label, payment_screenshot, payment_status, product,
                        amount, razorpay_order_id, razorpay_payment_id, razorpay_signature
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'razorpay_verified', 'Accepted', 'free_deposit', ?, ?, ?, ?)
                    """,
                    (
                        app_row["id"] if app_row else None, now, acct["name"], email,
                        acct["phone"], acct["city"], acct["college"], acct["course"],
                        acct["semester"], acct["year_of_passing"], domain_to_save,
                        joining_date, batch_label, int(UPI_AMOUNT), order_id, payment_id, signature
                    )
                )
                if app_row:
                    try:
                        transition_application(
                            conn=conn,
                            application_id=app_row["id"],
                            target_status=STATUS_ENROLLED,
                            actor="razorpay_gateway",
                            actor_role="system",
                            reason="Security deposit verified online via Razorpay",
                            request_id=req_id
                        )
                    except ApplicationStateMachineError as sme:
                        log_info("state_transition_skip", f"App {app_row['id']} transition in razorpay verify: {sme}")

                PaymentService.record_payment_event(conn, f"pay_{payment_id}", "payment.accepted", order_id, payment_id, data)
                conn.commit()
                send_enrollment_confirmation_email(acct["name"], email, domain_to_save, joining_date)
                return jsonify({"status": "success", "message": "Security deposit verified! Welcome to DBERT.", "redirect": "/portal"})

            elif product_type == "paid_program":
                batch_label = make_batch_label(joining_date) if joining_date else ""
                domain_to_save = domain or (app_row["domain"] if app_row else "")
                conn.execute(
                    """
                    INSERT INTO enrollments (
                        application_id, timestamp, name, email, phone, city, college,
                        course, semester, year_of_passing, domain, joining_date,
                        batch_label, payment_screenshot, payment_status, product,
                        amount, razorpay_order_id, razorpay_payment_id, razorpay_signature
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'razorpay_verified', 'Accepted', 'paid_program', ?, ?, ?, ?)
                    """,
                    (
                        app_row["id"] if app_row else None, now, acct["name"], email,
                        acct["phone"], acct["city"], acct["college"], acct["course"],
                        acct["semester"], acct["year_of_passing"], domain_to_save,
                        joining_date, batch_label, int(PAID_PROGRAM_AMOUNT), order_id, payment_id, signature
                    )
                )
                PaymentService.record_payment_event(conn, f"pay_{payment_id}", "payment.accepted", order_id, payment_id, data)
                conn.commit()
                send_enrollment_confirmation_email(acct["name"], email, domain_to_save, joining_date)
                return jsonify({"status": "success", "message": "Paid Enrollment confirmed! Welcome to DBERT.", "redirect": "/portal"})

        return jsonify({"status": "error", "message": "Unhandled product type"}), 400
    except Exception as e:
        log_error("razorpay_verify_payment", e)
        return jsonify({"status": "error", "message": "Internal error verifying payment"}), 500
