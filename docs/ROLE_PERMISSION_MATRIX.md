# DBERT Internship Portal — Role Permission & Authorization Matrix

**Document Date:** 2026-09-25  
**Specification:** Phase 11 — Authorization & Anti-IDOR Enforcement  
**Applicable Scope:** `Internshipportal4` Local Production-Grade Architecture  

---

## 1. System Roles Inventory

The portal defines 6 discrete security principles across all authenticated realms:

| Role Identifier | Authentication Method | Primary Database Table | Description |
|---|---|---|---|
| **`visitor` / `public`** | Unauthenticated | None | Anonymous visitors, public job/internship board viewers, applicants. |
| **`intern`** | Cookie (`dbert_auth`) → `user_sessions.role = 'intern'` | `intern_accounts` | Candidates, applicants, and enrolled students. |
| **`company`** | Cookie (`dbert_auth`) → `user_sessions.role = 'company'` | `companies` | Hiring partners posting jobs/internships and reviewing applicants. |
| **`mentor`** | Cookie (`dbert_auth`) → `user_sessions.role = 'mentor'` | `mentors` | Domain mentors reviewing tasks, interviews, and guidance. |
| **`staff`** | Session (`session['staff_id']`) + `staff_queue_roles` | `staff_accounts` | Operations staff handling review queues (courses, applications, projects). |
| **`admin`** | Cookie / Session (`user_sessions.role = 'admin'`, `session['admin_id']`) | `staff_accounts` / Env Admin | Superusers with complete administrative authority over all resources. |

---

## 2. Core Access Control Principles

1. **Authentication Gate**: Every non-public endpoint checks for a valid, non-expired session (`get_current_user()` or `require_admin()` or `current_staff()`). Invalid or expired sessions return HTTP `401 Unauthorized` (or redirect to login for browser page GETs).
2. **Vertical Authorization (Role-Based Access Control / RBAC)**: Each endpoint enforces minimum role level (`require_role("intern")`, `require_role("company")`, `require_role("mentor")`, `require_admin()`, `current_staff()`). Lower-tier roles attempting access receive HTTP `403 Forbidden` or `401 Unauthorized`.
3. **Horizontal Authorization (Anti-IDOR / Object Ownership)**: A user authenticated with a valid role **CANNOT** read, modify, or delete another user's resources. All queries for private data must bind `WHERE email = current_user.email` or `WHERE intern_id = current_intern.id`. Never trust user-supplied IDs (e.g. `POST /intern/update-profile`, `GET /intern/me`, `POST /intern/save-wizard-step`).
4. **Server-Side Transition Guards**: State changes (application status, enrollment status, payments) must go through state machine services (`services/application_service.py`, `services/enrollment_service.py`, `services/razorpay_client.py`) with explicit role checks.

---

## 3. Comprehensive Permission & Ownership Matrix

| Resource Domain | Route / Action | Method | Allowed Roles | Horizontal Ownership Constraint |
|---|---|---|---|---|
| **Authentication** | `/apply` | `POST` | `public` | Creates new intern account or validates existing session ownership. |
| | `/signup/stage1` | `POST` | `public` | Uniqueness on email and phone. Rate limited. |
| | `/intern/login` | `POST` | `public` | Validates credentials against `intern_accounts`. |
| | `/company/login` | `POST` | `public` | Validates credentials against `companies`. |
| | `/mentor/login` | `POST` | `public` | Validates credentials against `mentors`. |
| | `/admin/login` | `POST` | `public` | Validates credentials against `staff_accounts` / admin key. |
| | `/staff/login` | `POST` | `public` | Validates credentials against `staff_accounts`. |
| | `/logout`, `/admin/logout` | `GET, POST` | `all` | Invalidates active token in `user_sessions`, clears cookies & session. |
| | `/forgot-password` | `POST` | `public` | Neutral enumeration response; no token leakage. |
| | `/reset-password` | `POST` | `public` | One-time token validation, token expiry, old session invalidation. |
| **Applications** | `/intern/me` | `GET` | `intern` | Scoped strictly to `current_intern['email']`. |
| | `/intern/my-applications` | `GET` | `intern` | Returns only rows where `email = current_intern['email']`. |
| | `/admin/applications` | `GET` | `admin` | Global administrative view. |
| | `/admin/update-application-status` | `POST` | `admin` | Central state machine transition check (`services/application_service.py`). |
| | `/mentor/applications` | `GET` | `mentor` | Scoped to mentor's assigned domain. |
| | `/mentor/update-status` | `POST` | `mentor` | State machine transition restricted to mentor-allowed transitions. |
| **Enrollments** | `/enroll`, `/paid/enroll` | `POST` | `intern` | Intern can only enroll their own accepted application (`email = current_user['email']`). |
| | `/admin/update-enrollment-status`| `POST` | `admin` | Central state machine transition check (`services/enrollment_service.py`). |
| | `/admin/csv/enrollments` | `GET` | `admin` | Global enrollment export. |
| **Payments** | `/api/payment/razorpay/create-order` | `POST` | `intern` | Application must belong to `current_intern['email']`. |
| | `/api/payment/razorpay/verify` | `POST` | `intern` | Application must belong to `current_intern['email']`. HMAC-SHA256 verified. |
| | `/api/payment/razorpay/webhook` | `POST` | `system` | Cryptographic signature `X-Razorpay-Signature` validation. Idempotent. |
| | `/admin/payment/verify` | `POST` | `admin` | Admin verification of manual/UPI payments. |
| **CV & Profiles** | `/intern/update-profile` | `POST` | `intern` | Mutates only `intern_accounts WHERE email = current_intern['email']`. Domain/email locked. |
| | `/portal/cv` | `GET, POST` | `intern` | Loads/updates CV strictly for `current_intern['id']`. |
| | `/cv/<slug>` | `GET` | `public` | Rendered only if `is_public = 1`. Returns 404/Access Denied if private. |
| | `/cv/<slug>.pdf` | `GET` | `public` | Rendered only if `is_public = 1`. |
| **Certificates** | `/portal/certificate/<cert_id>` | `GET` | `public` | Public cryptographic certificate verification. |
| | `/api/intern/certificates` | `GET` | `intern` | Scoped strictly to `intern_id = current_intern['id']`. |
| | `/admin/issue-certificate` | `POST` | `admin` | Admin-only issuance. |
| **Messaging** | `/messages`, `/portal/messages` | `GET` | `intern, company, mentor, admin` | Lists only conversations where current actor is participant. |
| | `/messages/<conv_id>` | `GET` | `intern, company, mentor, admin` | IDOR Guard: User must be `intern_id` or `counterparty_id` in conversation. |
| | `/messages/<conv_id>/send` | `POST` | `intern, company, mentor, admin` | IDOR Guard: Sender must be a participant in conversation. |
| | `/messages/<conv_id>/poll` | `GET` | `intern, company, mentor, admin` | IDOR Guard: Poller must be a participant in conversation. |
| **Tasks & LMS** | `/intern/tasks` | `GET` | `intern` | Scoped to intern's enrolled domain courses. |
| | `/intern/task/<id>/submit` | `POST` | `intern` | Task submission stamped with `current_intern['id']`. |
| | `/intern/task-submissions` | `GET` | `intern` | Scoped strictly to `intern_id = current_intern['id']`. |
| | `/intern/learning-progress` | `GET` | `intern` | Scoped strictly to `intern_id = current_intern['id']`. |
| | `/mentor/task-submissions` | `GET` | `mentor` | Scoped to mentor's domain interns. |
| | `/admin/task-submissions` | `GET` | `admin` | Global task review. |
| **Company Jobs**| `/company/dashboard` | `GET` | `company` | Scoped strictly to `current_company['id']`. |
| | `/company/posts/new` | `POST` | `company` | Created with `company_id = current_company['id']`. |
| | `/company/posts/<id>/edit` | `POST` | `company` | IDOR Guard: `company_id = current_company['id']`. |
| | `/company/candidates` | `GET` | `company` | Only candidates who applied to posts owned by `current_company['id']`. |
| **Staff & Admin** | `/staff/*` | `GET, POST` | `staff` | Staff accounts with relevant queue permission (`staff_queue_roles`). |
| | `/admin/*` | `GET, POST` | `admin` | Full admin privileges. |

---

## 4. Automated Test Verification Matrix

All permissions and anti-IDOR constraints documented above are validated by two comprehensive automated regression suites:

1. **`tests/test_auth_regression.py`** (Phase 10):
   - Multi-role login validation (`intern`, `company`, `mentor`, `staff`, `admin`).
   - Duplicate email rejection on signup.
   - Duplicate phone rejection on signup.
   - Password reset lifecycle: token generation, neutral enumeration response, expiration enforcement, replay prevention, old session revocation.
   - Session logout invalidation and browser-back button cache/session denial.
   - Multi-tab session concurrency.

2. **`tests/test_idor_matrix.py`** (Phase 11):
   - Horizontal isolation between Intern A and Intern B (profiles, applications, CVs, task submissions, private conversations, learning progress).
   - Horizontal isolation between Company A and Company B (job postings, private candidate applications, feedback notes).
   - Vertical privilege escalation blocks: interns and companies blocked from `/admin/*` and `/staff/*`.
   - Vertical privilege escalation blocks: mentors blocked from administrative actions.
   - Unauthenticated access blocks across all protected endpoints.
