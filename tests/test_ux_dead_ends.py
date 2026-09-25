"""
Phase 17: UX Dead-End & Error Resolution Test Suite
Verifies:
  1. All error responses (400, 401, 403, 404, 410, 500) answer:
     - What happened
     - Why
     - What the user can do
  2. Zero raw stack traces leaked to users on 500 errors.
  3. JSON API errors include structured recovery action fields.
  4. Empty states across listings and dashboards provide clickable recovery links.
  5. Unauthenticated dashboards redirect cleanly to login without redirect loops.
"""

import pytest
import os
from unittest.mock import patch
from app import app
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


class TestErrorPagesAndResolution:
    """Verifies that all error pages explain what happened, why, and what to do next without dead ends."""

    def test_404_error_page_answers_what_why_and_next(self, app_client):
        client, _ = app_client
        logout(client)

        resp = client.get("/this-page-does-not-exist-xyz123")
        assert resp.status_code == 404

        html = resp.data.decode("utf-8")
        assert "Error 404" in html
        assert "Page Not Found" in html
        assert "What happened:" in html
        assert "Why:" in html
        assert "What you can do:" in html

        # Verify active recovery links
        assert 'href="/"' in html
        assert 'href="/portal"' in html
        assert 'href="/jobs"' in html
        assert "careers@dbert.info" in html

    def test_401_error_handler_answers_what_why_and_next(self, app_client):
        from app import unauthorized
        with app.test_request_context("/test-401", headers={"Accept": "text/html"}):
            resp, status_code = unauthorized(None)
            assert status_code == 401
            html = resp if isinstance(resp, str) else resp.get_data(as_text=True)
            assert "Error 401" in html
            assert "Authentication Required" in html
            assert "What happened:" in html
            assert "Why:" in html
            assert "What you can do:" in html
            assert 'href="/"' in html
            assert 'href="/portal"' in html

    def test_403_error_handler_answers_what_why_and_next(self, app_client):
        from app import forbidden
        with app.test_request_context("/test-403", headers={"Accept": "text/html"}):
            resp, status_code = forbidden(None)
            assert status_code == 403
            html = resp if isinstance(resp, str) else resp.get_data(as_text=True)
            assert "Error 403" in html
            assert "Access Forbidden" in html
            assert "What happened:" in html
            assert "Why:" in html
            assert "What you can do:" in html

    def test_410_gone_error_page_provides_active_listings_cta(self, app_client):
        from app import gone
        with app.test_request_context("/test-410", headers={"Accept": "text/html"}):
            resp, status_code = gone(None)
            assert status_code == 410
            html = resp if isinstance(resp, str) else resp.get_data(as_text=True)
            assert "Error 410" in html
            assert "Listing No Longer Available" in html
            assert "What happened:" in html
            assert "What you can do:" in html
            assert 'href="/jobs"' in html

    def test_500_error_page_never_leaks_raw_stack_trace(self, app_client):
        from app import internal_server_error
        with app.test_request_context("/test-500", headers={"Accept": "text/html"}):
            resp, status_code = internal_server_error(RuntimeError("Simulated system failure"))
            assert status_code == 500
            html = resp if isinstance(resp, str) else resp.get_data(as_text=True)
            assert "Error 500" in html
            assert "Something Went Wrong" in html
            assert "What happened:" in html
            assert "Why:" in html
            assert "What you can do:" in html
            # Zero raw exception leakage
            assert "Traceback" not in html
            assert "Simulated system failure" not in html
            assert 'href="/"' in html

    def test_json_error_responses_include_structured_recovery_action(self, app_client):
        client, _ = app_client

        resp = client.get("/api/non-existent-api-endpoint", headers={"Accept": "application/json"})
        assert resp.status_code == 404
        assert resp.is_json

        data = resp.get_json()
        assert data["status"] == "error"
        assert data["code"] == 404
        assert "heading" in data
        assert "message" in data
        assert "what_happened" in data
        assert "why" in data
        assert "action" in data


class TestNavigationAndNoDeadEnds:
    """Verifies that navigation flows and empty states guide the user cleanly with zero dead ends."""

    def test_unauthenticated_portal_redirects_to_signin(self, app_client):
        client, _ = app_client
        logout(client)

        resp = client.get("/portal")
        assert resp.status_code == 302
        assert "/#signin" in resp.headers["Location"]

    def test_unauthenticated_company_redirects_to_login(self, app_client):
        client, _ = app_client
        logout(client)

        resp = client.get("/company")
        assert resp.status_code in (302, 401)
        if resp.status_code == 302:
            assert "/company/login" in resp.headers["Location"]

    def test_unauthenticated_staff_redirects_to_login(self, app_client):
        client, _ = app_client
        logout(client)

        resp = client.get("/staff/dashboard")
        assert resp.status_code in (302, 401)
        if resp.status_code == 302:
            assert "/staff/login" in resp.headers["Location"]

    def test_unauthenticated_admin_redirects_to_login(self, app_client):
        client, _ = app_client
        logout(client)

        resp = client.get("/admin")
        assert resp.status_code in (302, 401)
        if resp.status_code == 302:
            assert "/admin-login" in resp.headers["Location"]

    def test_empty_jobs_listing_has_clickable_browse_all_link(self, app_client):
        client, _ = app_client

        resp = client.get("/jobs?domain=CompletelyAbsentDomain999")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert 'href="/jobs"' in html
        assert "browse all" in html

    def test_empty_internships_listing_has_clickable_browse_all_link(self, app_client):
        client, _ = app_client

        resp = client.get("/internships?domain=CompletelyAbsentDomain999")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert 'href="/internships"' in html
        assert "browse all" in html

    def test_invalid_certificate_id_provides_support_and_qr_guidance(self, app_client):
        client, _ = app_client

        resp = client.get("/portal/certificate/NON-EXISTENT-CERT-ID-12345")
        assert resp.status_code == 404
        html = resp.data.decode("utf-8")
        assert "Could not verify" in html
        assert "Please check the ID or QR code" in html
        assert "https://wa.me/917060372107" in html
