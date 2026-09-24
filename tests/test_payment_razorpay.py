"""
tests/test_payment_razorpay.py - Comprehensive Unit & Integration Tests
for Razorpay Payment Gateway & Dynamic Fallback (Phase 8, PAY-001 - PAY-004)
"""

import os
import hmac
import hashlib
import json
import pytest
from unittest.mock import patch, MagicMock
from services.razorpay_client import (
    is_razorpay_enabled,
    get_public_config,
    verify_payment_signature,
    verify_webhook_signature,
    create_order,
    RazorpayNotConfiguredError,
    RazorpayAPIError
)
from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_client() as client:
        yield client


class TestRazorpayClient:
    def test_disabled_by_default_without_keys(self, monkeypatch):
        """When keys are not set, is_razorpay_enabled() is False and fallback is active."""
        monkeypatch.delenv("RAZORPAY_KEY_ID", raising=False)
        monkeypatch.delenv("RAZORPAY_KEY_SECRET", raising=False)

        assert is_razorpay_enabled() is False
        cfg = get_public_config()
        assert cfg["enabled"] is False
        assert cfg["key_id"] == ""
        assert cfg["fallback_available"] is True

    def test_enabled_when_keys_present(self, monkeypatch):
        """When valid keys are set, is_razorpay_enabled() is True."""
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_123456789")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "test_secret_abcdef")
        monkeypatch.setenv("RAZORPAY_ENABLED", "1")

        assert is_razorpay_enabled() is True
        cfg = get_public_config()
        assert cfg["enabled"] is True
        assert cfg["key_id"] == "rzp_test_123456789"

    def test_explicitly_disabled_flag(self, monkeypatch):
        """Even if keys exist, RAZORPAY_ENABLED=0 disables the gateway for fallback."""
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_123456789")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "test_secret_abcdef")
        monkeypatch.setenv("RAZORPAY_ENABLED", "0")

        assert is_razorpay_enabled() is False

    def test_signature_verification_success(self, monkeypatch):
        """Valid HMAC-SHA256 signature returns True."""
        secret = "super_secret_test_key"
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_123")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", secret)

        order_id = "order_9A33XWu170gUtm"
        payment_id = "pay_29QQoUBi66xm2f"
        msg = f"{order_id}|{payment_id}".encode("utf-8")
        valid_sig = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()

        assert verify_payment_signature(order_id, payment_id, valid_sig) is True

    def test_signature_verification_failure_tampered(self, monkeypatch):
        """Tampered or invalid signature returns False."""
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_123")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "super_secret_test_key")

        order_id = "order_9A33XWu170gUtm"
        payment_id = "pay_29QQoUBi66xm2f"
        tampered_sig = "abcdef1234567890badsignature"

        assert verify_payment_signature(order_id, payment_id, tampered_sig) is False

    def test_webhook_signature_verification(self, monkeypatch):
        """Webhook HMAC signature verification passes with matching secret."""
        webhook_sec = "whsec_test_secret_789"
        monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", webhook_sec)

        payload = b'{"event":"payment.captured","payload":{}}'
        valid_sig = hmac.new(webhook_sec.encode("utf-8"), payload, hashlib.sha256).hexdigest()

        assert verify_webhook_signature(payload, valid_sig) is True
        assert verify_webhook_signature(payload, "invalid_sig") is False

    def test_create_order_without_keys_raises(self, monkeypatch):
        """Calling create_order when gateway is disabled raises RazorpayNotConfiguredError."""
        monkeypatch.delenv("RAZORPAY_KEY_ID", raising=False)
        monkeypatch.delenv("RAZORPAY_KEY_SECRET", raising=False)

        with pytest.raises(RazorpayNotConfiguredError):
            create_order(amount_inr=499, receipt="rcpt_1")

    @patch("requests.post")
    def test_create_order_success(self, mock_post, monkeypatch):
        """Mocked order creation returns canonical amount in paise and order_id."""
        monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_123")
        monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret_123")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "order_test_987", "amount": 49900, "currency": "INR"}
        mock_post.return_value = mock_resp

        order = create_order(amount_inr=499, receipt="rcpt_1")
        assert order["order_id"] == "order_test_987"
        assert order["amount"] == 49900
        assert order["currency"] == "INR"
        assert order["key_id"] == "rzp_test_123"


class TestPaymentEndpoints:
    def test_api_payment_config_endpoint(self, app_client):
        """GET /api/payment/config returns 200 with JSON payload."""
        client, _ = app_client
        res = client.get("/api/payment/config")
        assert res.status_code == 200
        data = res.get_json()
        assert "enabled" in data
        assert "fallback_available" in data

    def test_api_create_order_unauthorized(self, app_client):
        """POST /api/payment/razorpay/create-order without auth returns 401 or 503."""
        client, _ = app_client
        res = client.post("/api/payment/razorpay/create-order", json={"product_type": "security_deposit"})
        assert res.status_code in (401, 503)

    def test_api_webhook_idempotency(self, app_client, monkeypatch):
        """POST /api/payment/razorpay/webhook ignores duplicate event IDs idempotently."""
        client, _ = app_client
        monkeypatch.delenv("RAZORPAY_WEBHOOK_SECRET", raising=False)
        event_payload = {
            "event_id": "evt_test_unique_123",
            "event": "payment.captured",
            "payload": {"payment": {"entity": {"id": "pay_test_1"}}}
        }

        # First post -> 200 OK
        res1 = client.post("/api/payment/razorpay/webhook", json=event_payload)
        assert res1.status_code == 200
        assert res1.get_json()["status"] == "ok"

        # Second post with identical event_id -> 200 OK with duplicate ignored
        res2 = client.post("/api/payment/razorpay/webhook", json=event_payload)
        assert res2.status_code == 200
        assert res2.get_json()["status"] == "ok"
        assert "Duplicate event ignored" in res2.get_json()["message"]
