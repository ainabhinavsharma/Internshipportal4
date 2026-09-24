import os
import json
import pytest
import datetime
from app import get_db, live_openings_total, _domain_tile_counts, _trust_stats, _LIVE_SQL
from tests.conftest import (
    seed_intern, login_as_intern, seed_company, login_as_company,
    seed_staff, login_as_admin, logout
)

class TestMarketplaceCompanyLifecycle:
    """Verifies company registration, approval, suspension, and authorization gates."""

    def test_company_registration_and_initial_unapproved_state(self, app_client):
        client, db_path = app_client
        os.environ["DB_FILE"] = db_path

        # 1. Company registration
        signup_resp = client.post("/company/signup", json={
            "name": "Acme Innovations Ltd",
            "email": "hr@acmeinnovations.com",
            "password": "SecurePassword123!",
            "phone": "9876543201",
            "website": "https://acmeinnovations.com",
            "city": "Bengaluru"
        })
        assert signup_resp.status_code in (200, 302)

        # 2. Check DB: company is created with is_approved=0
        with get_db() as conn:
            company = conn.execute("SELECT * FROM companies WHERE email='hr@acmeinnovations.com'").fetchone()
            assert company is not None
            assert company["is_approved"] == 0
            assert company["is_active"] == 1
            company_id = company["id"]

        # 3. Log in as newly registered company
        login_resp = client.post("/company/login", json={
            "email": "hr@acmeinnovations.com",
            "password": "SecurePassword123!"
        })
        assert login_resp.status_code == 200

        # 4. Create draft post
        create_resp = client.post("/company/posts", json={
            "post_type": "job",
            "domain": "AI Agent Development",
            "title": "Junior AI Automation Engineer",
            "description": "We are seeking a talented Junior AI Automation Engineer to design, build, and deploy production-grade agentic workflows with LangGraph and Flask.",
            "skills": "Python, Flask, LLMs, Agents",
            "location": "Bengaluru",
            "work_mode": "hybrid",
            "stipend_min": 40000,
            "stipend_max": 60000,
            "openings": 3
        })
        assert create_resp.status_code == 200
        post_id = create_resp.get_json()["post_id"]

        # 5. Unapproved company cannot publish post (403 Forbidden)
        pub_resp = client.post(f"/company/posts/{post_id}/publish")
        assert pub_resp.status_code == 403
        assert "pending admin approval" in pub_resp.get_json()["message"].lower()

    def test_admin_approval_and_suspension_controls(self, app_client):
        client, db_path = app_client
        os.environ["DB_FILE"] = db_path

        # Seed company with is_approved=0
        comp_id = seed_company(db_path, email="alpha@corp.com", password="AlphaPassword123!", name="Alpha Corp", is_approved=0, is_active=1)

        # Log in as admin
        login_as_admin(client, db_path, email="admin_market@dbert.org", password="AdminPass123!")

        # 1. Admin approves company
        appr_resp = client.post("/admin/companies/approve", json={"company_id": comp_id, "approve": True})
        assert appr_resp.status_code == 200
        assert appr_resp.get_json()["is_approved"] == 1

        with get_db() as conn:
            c_row = conn.execute("SELECT is_approved, is_active FROM companies WHERE id=?", (comp_id,)).fetchone()
            assert c_row["is_approved"] == 1

        # 2. Company logs in and creates + publishes post
        logout(client)
        login_as_company(client, db_path, email="alpha@corp.com", password="AlphaPassword123!", name="Alpha Corp")

        create_resp = client.post("/company/posts", json={
            "post_type": "job",
            "domain": "Full Stack Development",
            "title": "Full Stack Python Developer",
            "description": "Looking for an experienced Full Stack Python Developer proficient in Flask, SQLite, and responsive modern user interfaces to join our scaling engineering unit.",
            "skills": "Python, Flask, JavaScript, SQLite",
            "work_mode": "remote",
            "stipend_min": 50000,
            "stipend_max": 75000,
            "openings": 2
        })
        assert create_resp.status_code == 200
        post_id = create_resp.get_json()["post_id"]

        pub_resp = client.post(f"/company/posts/{post_id}/publish")
        assert pub_resp.status_code == 200
        assert pub_resp.get_json()["post_status"] == "published"

        # Check post is live in public directory
        logout(client)
        jobs_resp = client.get("/jobs")
        assert jobs_resp.status_code == 200
        assert "Full Stack Python Developer" in jobs_resp.get_data(as_text=True)

        # 3. Admin suspends company
        login_as_admin(client, db_path, email="admin_market@dbert.org", password="AdminPass123!")
        susp_resp = client.post("/admin/companies/suspend", json={"company_id": comp_id, "suspend": True})
        assert susp_resp.status_code == 200
        assert susp_resp.get_json()["is_active"] == 0

        # Post automatically disappears from public directory because company is not active
        logout(client)
        jobs_resp2 = client.get("/jobs")
        assert jobs_resp2.status_code == 200
        assert "Full Stack Python Developer" not in jobs_resp2.get_data(as_text=True)

        # Public post detail aborts with 410 (Gone)
        post_detail = client.get(f"/jobs/{post_id}", follow_redirects=True)
        assert post_detail.status_code == 410

        # 4. Admin un-suspends company
        login_as_admin(client, db_path, email="admin_market@dbert.org", password="AdminPass123!")
        unsusp_resp = client.post("/admin/companies/suspend", json={"company_id": comp_id, "suspend": False})
        assert unsusp_resp.status_code == 200
        assert unsusp_resp.get_json()["is_active"] == 1

        # Post is live again
        logout(client)
        jobs_resp3 = client.get("/jobs")
        assert jobs_resp3.status_code == 200
        assert "Full Stack Python Developer" in jobs_resp3.get_data(as_text=True)


class TestMarketplaceListingLifecycle:
    """Verifies listing creation, Google-for-Jobs gates, publishing, slots, expiring, unpublishing, and deletion."""

    def test_completeness_gate_and_publishing_lifecycle(self, app_client):
        client, db_path = app_client
        os.environ["DB_FILE"] = db_path

        comp_id = seed_company(db_path, email="beta@corp.com", password="BetaPassword123!", name="Beta Tech", is_approved=1, is_active=1)
        login_as_company(client, db_path, email="beta@corp.com", password="BetaPassword123!", name="Beta Tech")

        # 1. Create post with description under 100 chars
        short_desc_resp = client.post("/company/posts", json={
            "post_type": "internship",
            "domain": "Data Analyst",
            "title": "Data Analyst Intern",
            "description": "Short desc under 100 chars.",
            "work_mode": "remote"
        })
        assert short_desc_resp.status_code == 200
        post_id = short_desc_resp.get_json()["post_id"]

        # Attempt to publish fails completeness check
        pub_fail = client.post(f"/company/posts/{post_id}/publish")
        assert pub_fail.status_code == 400
        fail_data = pub_fail.get_json()
        assert fail_data.get("code") == "incomplete"
        assert any("100 characters" in f for f in fail_data.get("fields", []))

        # 2. Update post to satisfy completeness requirements
        full_desc = "We are seeking a highly motivated Data Analyst Intern to assist with automated business dashboards, query optimization, and predictive reporting models."
        assert len(full_desc) >= 100

        update_resp = client.post("/company/posts", json={
            "post_id": post_id,
            "post_type": "internship",
            "domain": "Data Analyst",
            "title": "Data Analyst Intern",
            "description": full_desc,
            "work_mode": "remote",
            "stipend_min": 15000,
            "stipend_max": 25000,
            "openings": 2
        })
        assert update_resp.status_code == 200

        # Draft post is not visible publicly (404)
        logout(client)
        draft_view = client.get(f"/internships/{post_id}")
        assert draft_view.status_code == 404

        # 3. Publish post
        login_as_company(client, db_path, email="beta@corp.com", password="BetaPassword123!", name="Beta Tech")
        pub_ok = client.post(f"/company/posts/{post_id}/publish")
        assert pub_ok.status_code == 200
        assert pub_ok.get_json()["post_status"] == "published"

        # Check published dates and live visibility
        with get_db() as conn:
            p_row = conn.execute("SELECT status, published_at, expires_at FROM posts WHERE id=?", (post_id,)).fetchone()
            assert p_row["status"] == "published"
            assert p_row["published_at"] is not None
            assert p_row["expires_at"] is not None

        logout(client)
        live_view = client.get(f"/internships/{post_id}")
        # Redirects 301 to canonical slug URL
        assert live_view.status_code == 301
        canonical_url = live_view.headers.get("Location")
        canon_view = client.get(canonical_url)
        assert canon_view.status_code == 200
        assert "Data Analyst Intern" in canon_view.get_data(as_text=True)

        # 4. Unpublish post
        login_as_company(client, db_path, email="beta@corp.com", password="BetaPassword123!", name="Beta Tech")
        unpub_resp = client.post(f"/company/posts/{post_id}/unpublish")
        assert unpub_resp.status_code == 200
        assert unpub_resp.get_json()["post_status"] == "unpublished"

        # Now unpublished: returns 410 Gone publicly
        logout(client)
        unpub_view = client.get(canonical_url)
        assert unpub_view.status_code == 410

    def test_maximum_3_live_posts_concurrency_guard(self, app_client):
        client, db_path = app_client
        os.environ["DB_FILE"] = db_path

        comp_id = seed_company(db_path, email="gamma@corp.com", password="GammaPassword123!", name="Gamma Labs", is_approved=1, is_active=1)
        login_as_company(client, db_path, email="gamma@corp.com", password="GammaPassword123!", name="Gamma Labs")

        valid_desc = "Extensive description meeting the Google-for-Jobs minimum one hundred character threshold for engineering job postings on the platform."

        post_ids = []
        for i in range(4):
            resp = client.post("/company/posts", json={
                "post_type": "job",
                "domain": "Python Automation",
                "title": f"Security Analyst Track {i+1}",
                "description": valid_desc,
                "work_mode": "remote",
                "openings": 1
            })
            assert resp.status_code == 200
            post_ids.append(resp.get_json()["post_id"])

        # Publish 1, 2, 3
        for pid in post_ids[:3]:
            pub_res = client.post(f"/company/posts/{pid}/publish")
            assert pub_res.status_code == 200

        # Attempt to publish 4th post fails with 409 conflict
        pub_4 = client.post(f"/company/posts/{post_ids[3]}/publish")
        assert pub_4.status_code == 409
        assert "already have 3 live posts" in pub_4.get_json()["message"]


class TestMarketplaceCandidateApplicationFlow:
    """Verifies candidate application, CTA controls, company review, shortlisting, and hiring."""

    def test_candidate_apply_and_status_progression(self, app_client):
        client, db_path = app_client
        os.environ["DB_FILE"] = db_path

        comp_id = seed_company(db_path, email="delta@corp.com", password="DeltaPassword123!", name="Delta Systems", is_approved=1, is_active=1)
        intern_id = seed_intern(db_path, email="candidate_delta@example.com", password="CandidatePass123!", name="Candidate Delta")

        # Company creates and publishes job
        login_as_company(client, db_path, email="delta@corp.com", password="DeltaPassword123!", name="Delta Systems")
        post_resp = client.post("/company/posts", json={
            "post_type": "job",
            "domain": "AI Agent Development",
            "title": "Lead Agent Engineer",
            "description": "Comprehensive engineering position leading the design and rollout of multi-agent distributed systems across enterprise clients.",
            "work_mode": "remote",
            "openings": 1
        })
        post_id = post_resp.get_json()["post_id"]
        client.post(f"/company/posts/{post_id}/publish")
        logout(client)

        # 1. Anonymous applicant receives 401 login_required
        anon_apply = client.post(f"/posts/{post_id}/apply", json={"comment": "Interested in applying"})
        assert anon_apply.status_code == 401
        assert anon_apply.get_json()["status"] == "login_required"

        # 2. Logged-in intern applies
        login_as_intern(client, db_path, email="candidate_delta@example.com", password="CandidatePass123!", name="Candidate Delta")
        apply_resp = client.post(f"/posts/{post_id}/apply", json={
            "comment": "Experienced in building autonomous workflows with Python and LangGraph."
        })
        assert apply_resp.status_code == 200
        assert apply_resp.get_json()["status"] == "success"

        with get_db() as conn:
            app_row = conn.execute("SELECT * FROM post_applications WHERE post_id=? AND intern_id=?", (post_id, intern_id)).fetchone()
            assert app_row is not None
            assert app_row["status"] == "Applied"
            pa_id = app_row["id"]

        # Re-applying updates comment idempotently
        reapply = client.post(f"/posts/{post_id}/apply", json={
            "comment": "Updated application statement with recent github project link."
        })
        assert reapply.status_code == 200
        with get_db() as conn:
            app_row2 = conn.execute("SELECT * FROM post_applications WHERE post_id=? AND intern_id=?", (post_id, intern_id)).fetchone()
            assert "recent github project link" in app_row2["comment"]

        logout(client)

        # 3. Company reviews applicant list
        login_as_company(client, db_path, email="delta@corp.com", password="DeltaPassword123!", name="Delta Systems")
        app_list_resp = client.get(f"/company/posts/{post_id}/applicants")
        assert app_list_resp.status_code == 200
        html = app_list_resp.get_data(as_text=True)
        assert "Candidate Delta" in html

        # 4. Company advances candidate: Shortlisted
        shortlist_resp = client.post(f"/company/applications/{pa_id}/status", json={"status": "Shortlisted"})
        assert shortlist_resp.status_code == 200
        assert shortlist_resp.get_json()["application_status"] == "Shortlisted"

        # 5. Company advances candidate: Hired
        hire_resp = client.post(f"/company/applications/{pa_id}/status", json={"status": "Hired"})
        assert hire_resp.status_code == 200
        assert hire_resp.get_json()["application_status"] == "Hired"

        with get_db() as conn:
            final_app = conn.execute("SELECT status FROM post_applications WHERE id=?", (pa_id,)).fetchone()
            assert final_app["status"] == "Hired"

    def test_expired_listing_rejects_application_and_hides_cta(self, app_client):
        client, db_path = app_client
        os.environ["DB_FILE"] = db_path

        comp_id = seed_company(db_path, email="epsilon@corp.com", password="EpsilonPass123!", name="Epsilon Soft", is_approved=1, is_active=1)
        intern_id = seed_intern(db_path, email="candidate_eps@example.com", password="CandidatePass123!", name="Candidate Eps")

        # Company creates post with expired timestamp
        past_date = (datetime.datetime.now() - datetime.timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
        with get_db() as conn:
            cur = conn.execute("""
                INSERT INTO posts (company_id, post_type, domain, title, slug, description,
                                   work_mode, openings, status, published_at, expires_at, created_at, updated_at)
                VALUES (?, 'job', 'AI Agent Development', 'Expired Quantum Engineer', 'expired-quantum-engineer',
                        'Detailed description exceeding one hundred characters in total length for this role.',
                        'remote', 1, 'published', ?, ?, ?, ?)
            """, (comp_id, past_date, past_date, past_date, past_date))
            post_id = cur.lastrowid
            conn.commit()

        # Public detail returns 410 (Gone) — never renders active apply button
        detail_resp = client.get(f"/jobs/{post_id}", follow_redirects=True)
        assert detail_resp.status_code == 410

        # Candidate attempting direct apply gets 400 "no longer accepting applications"
        login_as_intern(client, db_path, email="candidate_eps@example.com", password="CandidatePass123!", name="Candidate Eps")
        apply_resp = client.post(f"/posts/{post_id}/apply", json={"comment": "Late applicant"})
        assert apply_resp.status_code == 400
        assert "no longer accepting applications" in apply_resp.get_json()["message"].lower()


class TestMarketplaceLiveDatabaseCounts:
    """Verifies that inventory counts come from live database state with zero hardcoding."""

    def test_live_openings_total_tracks_real_database_state(self, app_client):
        client, db_path = app_client
        os.environ["DB_FILE"] = db_path

        # Clear existing posts and referencing records
        with get_db() as conn:
            conn.execute("DELETE FROM post_applications")
            conn.execute("DELETE FROM post_comments")
            conn.execute("DELETE FROM post_questions")
            conn.execute("DELETE FROM posts")
            conn.commit()

        # Reset openings cache
        import app
        app._OPENINGS_CACHE = {"at": 0.0, "total": 0}

        # Initially 0 live posts
        assert live_openings_total() == 0

        # Create approved company
        comp_id = seed_company(db_path, email="live_stat@corp.com", password="StatPass123!", name="Stat Corp", is_approved=1, is_active=1)

        # Insert 2 live posts with 5 and 10 openings
        future_date = (datetime.datetime.now() + datetime.timedelta(days=20)).strftime("%Y-%m-%d %H:%M:%S")
        with get_db() as conn:
            conn.execute("""
                INSERT INTO posts (company_id, post_type, domain, title, slug, description,
                                   work_mode, openings, status, published_at, expires_at, created_at, updated_at)
                VALUES (?, 'job', 'AI Agent Development', 'Role 1', 'role-1', 'Valid description over 100 characters in length for testing metrics.',
                        'remote', 5, 'published', datetime('now'), ?, datetime('now'), datetime('now'))
            """, (comp_id, future_date))
            conn.execute("""
                INSERT INTO posts (company_id, post_type, domain, title, slug, description,
                                   work_mode, openings, status, published_at, expires_at, created_at, updated_at)
                VALUES (?, 'job', 'AI Agent Development', 'Role 2', 'role-2', 'Valid description over 100 characters in length for testing metrics.',
                        'remote', 10, 'published', datetime('now'), ?, datetime('now'), datetime('now'))
            """, (comp_id, future_date))
            conn.commit()

        # Reset cache to force recalculation
        app._OPENINGS_CACHE = {"at": 0.0, "total": 0}
        # Formula: int(total * 0.9) -> (5 + 10) * 0.9 = 13
        assert live_openings_total() == 13

        # Add draft post with 20 openings -> draft MUST NOT affect live total
        with get_db() as conn:
            conn.execute("""
                INSERT INTO posts (company_id, post_type, domain, title, slug, description,
                                   work_mode, openings, status, created_at, updated_at)
                VALUES (?, 'job', 'AI Agent Development', 'Draft Role', 'draft-role', 'Draft description.',
                        'remote', 20, 'draft', datetime('now'), datetime('now'))
            """, (comp_id,))
            conn.commit()

        app._OPENINGS_CACHE = {"at": 0.0, "total": 0}
        assert live_openings_total() == 13

        # When company is suspended (is_active=0), posts drop from live count
        with get_db() as conn:
            conn.execute("UPDATE companies SET is_active=0 WHERE id=?", (comp_id,))
            conn.commit()

        app._OPENINGS_CACHE = {"at": 0.0, "total": 0}
        assert live_openings_total() == 0
