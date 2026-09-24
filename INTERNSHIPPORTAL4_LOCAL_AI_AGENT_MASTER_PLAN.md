# Internshipportal4 — Local AI Agent Master Development Plan

**Repository target:** `https://github.com/ainabhinavsharma/Internshipportal4`  
**Source/reference repository:** `https://github.com/ainabhinavsharma/Internshipportal`  
**Execution mode:** LOCAL DEVELOPMENT ONLY → TEST → COMMIT → PUSH  
**Production rule:** NEVER connect the local agent directly to production systems or production databases.

---

# 0. MISSION

You are the local AI development agent responsible for taking the existing DBERT Internship Portal implementation from:

`https://github.com/ainabhinavsharma/Internshipportal`

and safely developing the next-generation/stabilized version in:

`https://github.com/ainabhinavsharma/Internshipportal4`

The target repository currently exists but is empty. Verify this yourself before doing anything destructive.

The objective is NOT to blindly copy the source repository and start rewriting it.

The objective is to:

1. inspect the source repository,
2. establish a verified baseline,
3. copy/import the required implementation into the local working repository,
4. preserve existing functionality and data compatibility,
5. add deterministic state machines,
6. harden payments,
7. improve testing/security/reliability,
8. evolve Guided Learning into Guided Learning 2.0,
9. document every change,
10. commit verified work,
11. push only verified commits to `Internshipportal4`.

---

# 1. ABSOLUTE OPERATING RULES

## 1.1 LOCAL FIRST

All development must happen locally.

Required flow:

```text
GitHub source
    ↓
LOCAL CLONE
    ↓
LOCAL AUDIT
    ↓
LOCAL IMPLEMENTATION
    ↓
LOCAL TESTS
    ↓
LOCAL SECURITY CHECKS
    ↓
LOCAL BUILD/SMOKE TEST
    ↓
COMMIT
    ↓
PUSH Internshipportal4
```

Never:

```text
AI agent → production server
AI agent → production DB
AI agent → production credentials
AI agent → production payment gateway
```

---

## 1.2 NEVER USE PRODUCTION CREDENTIALS

Do not copy:

- production `.env`
- production database
- production API keys
- production payment secrets
- production SMTP credentials
- production AI credentials
- production storage credentials

Use:

```text
.env.example
.env.local
test credentials
mock credentials
sandbox credentials
```

Secrets must never be committed.

---

# 2. TARGET REPOSITORY RULE

The only GitHub repository that the agent is authorized to update is:

```text
https://github.com/ainabhinavsharma/Internshipportal4
```

The source repository is:

```text
https://github.com/ainabhinavsharma/Internshipportal
```

Treat the source repository as the reference implementation.

Do NOT push development work to the source repository.

Do NOT force-push.

Do NOT rewrite history.

Do NOT delete the target repository history unless explicitly authorized.

---

# 3. FIRST SESSION — MANDATORY PREFLIGHT

Before modifying any source file:

```bash
git status
git remote -v
git branch --show-current
git log --oneline -10
```

Then verify:

```bash
git ls-remote https://github.com/ainabhinavsharma/Internshipportal.git
git ls-remote https://github.com/ainabhinavsharma/Internshipportal4.git
```

Clone both repositories into separate local directories.

Example:

```bash
git clone https://github.com/ainabhinavsharma/Internshipportal.git Internshipportal-source
git clone https://github.com/ainabhinavsharma/Internshipportal4.git Internshipportal4
```

If `Internshipportal4` is empty, initialize the working tree using the source implementation only after recording that fact.

Never assume the target is empty. Verify.

---

# 4. REQUIRED PREFLIGHT REPORT

Create:

```text
.agent/PREFLIGHT.md
```

Include:

```text
source repository
target repository
source branch
target branch
source commit SHA
target commit SHA
working directory
Python version
pip version
Node version if applicable
OS
database engine
test command
lint command
build command
environment files detected
secrets detected
production-looking credentials detected
git remotes
git status
```

The report must explicitly state:

```text
PRODUCTION ACCESS: NOT USED
PRODUCTION DATABASE: NOT USED
PRODUCTION CREDENTIALS: NOT USED
```

If this cannot be guaranteed, STOP.

---

# 5. SOURCE REPOSITORY BASELINE

Before importing or modifying code, inspect:

```text
README.md
AGENTS.md
CHANGELOG.md
requirements*.txt
pyproject.toml
pytest.ini
package*.json
Dockerfile*
docker-compose*
.github/
tests/
routes/
services/
templates/
static/
scripts/
migrations/
database/
```

Also inspect the main application entry point.

The source repository is a large Flask application and must be treated as an existing production-oriented system, not a greenfield project.

Do not rewrite `app.py` simply because it is large.

---

# 6. BASELINE DOCUMENTATION

Create:

```text
docs/
├── PROJECT_STATE.md
├── DEVELOPMENT_PLAN.md
├── CURRENT_PHASE.md
├── ROUTE_INVENTORY.md
├── FEATURE_INVENTORY.md
├── DATABASE_INVENTORY.md
├── EXTERNAL_SERVICES.md
├── STATE_MACHINES.md
├── ROLE_PERMISSION_MATRIX.md
├── ROUTE_COMPATIBILITY.md
├── QA_MASTER_PLAN.md
├── DATABASE_SAFETY.md
├── RELEASE_PROCESS.md
├── ROLLBACK_PLAN.md
├── INCIDENT_RUNBOOK.md
└── GUIDED_LEARNING_V2.md
```

Create:

```text
.agent/
├── CURRENT_PHASE.md
├── TASK_QUEUE.md
├── COMPLETED.md
├── BLOCKED.md
├── DECISIONS.md
├── TEST_RESULTS.md
├── FILES_CHANGED.md
├── SESSION_LOG.md
└── PREFLIGHT.md
```

---

# 7. AGENT SESSION PROTOCOL

At the beginning of EVERY session:

1. Read `.agent/CURRENT_PHASE.md`
2. Read `.agent/TASK_QUEUE.md`
3. Read `.agent/BLOCKED.md`
4. Read `.agent/DECISIONS.md`
5. Read relevant `docs/`
6. Run `git status`
7. Inspect uncommitted changes
8. Determine current phase
9. Select highest-priority unblocked task
10. Inspect existing implementation before changing it

At the end:

1. Run tests
2. Record test results
3. Record files changed
4. Record failures
5. Record decisions
6. Update task state
7. Update current phase
8. Update migration status if applicable
9. Update session log
10. Commit only verified work

If a session stops unexpectedly, resume from the last `VERIFIED` task.

---

# 8. TASK STATE MODEL

Every task must use:

```text
DISCOVERED
READY
IN_PROGRESS
BLOCKED
IMPLEMENTED
TESTING
VERIFIED
RELEASED
REGRESSION
```

Never mark a task complete merely because code exists.

Definition:

```text
IMPLEMENTED = code exists
TESTING = tests are executing
VERIFIED = tests and required review pass
RELEASED = verified commit pushed to target repository
```

---

# 9. PHASE 0 — VERIFIED SYSTEM INVENTORY

## Objective

Understand the source before changing it.

### INV-001 Route Inventory

Record for every route:

```text
route
method
authentication
role
ownership requirement
purpose
tables
external services
response/template
redirects
error states
tests
```

### INV-002 Feature Inventory

Classify:

```text
ACTIVE
PARTIAL
LEGACY
UNKNOWN
BROKEN
UNUSED
```

Categories:

```text
authentication
profile
application
selection
enrollment
payment
LMS
courses
quizzes
tasks
projects
mentor
company
marketplace
certificates
CV
AI interview
messaging
notifications
referrals
admin
analytics
security
SEO
guided learning
```

### INV-003 Database Inventory

Document:

```text
tables
columns
indexes
constraints
foreign keys
relationships
migrations
seed data
legacy tables
duplicated concepts
status fields
payment fields
learning fields
```

### INV-004 External Services

Document:

```text
email
AI
payment
storage
OAuth
CAPTCHA
analytics
other APIs
```

For each:

```text
provider
purpose
credential source
timeout
retry
fallback
failure behavior
staging behavior
production dependency
```

### Gate 0

Do not proceed until:

- route inventory exists
- feature inventory exists
- database inventory exists
- external service inventory exists
- critical unknown dependencies are identified

---

# 10. PHASE 1 — SAFE IMPORT INTO INTERNSHIPPORTAL4

If target repository is empty:

1. preserve target Git metadata,
2. import the verified source working tree,
3. create an initial baseline commit,
4. tag it:

```text
baseline/source-import
```

Do not import:

```text
.env
production DB
uploads containing private users
secrets
credentials
private certificates
production logs
```

Create:

```text
.env.example
```

The first target-repository commit should represent:

```text
SOURCE BASELINE — NO FUNCTIONAL CHANGES
```

Verify the application runs locally before continuing.

---

# 11. PHASE 2 — LOCAL DEVELOPMENT SAFETY

Create:

```text
scripts/verify_env_safety.py
```

It must fail if it detects:

```text
production database paths
production credentials
Razorpay live keys
production SMTP credentials
AWS production secrets
private API tokens
hardcoded passwords
private certificates
```

Add secret scanning where practical.

CI must reject committed secrets.

---

# 12. PHASE 3 — TEST BASELINE

Before major changes:

```bash
pytest
```

Run all existing test suites.

If Playwright exists:

```bash
npx playwright test
```

If frontend build exists:

```bash
npm test
npm run build
```

Use the actual commands discovered from the repository; do not invent commands when the repository provides alternatives.

Create:

```text
.agent/BASELINE_TEST_RESULTS.md
```

Record:

```text
test
passed
failed
skipped
environment failures
known defects
```

Never hide baseline failures.

---

# 13. PHASE 4 — PRODUCTION SAFETY FOUNDATION

Implement locally:

## SAFE-001 Backup

Create backup tooling for SQLite or the actual DB discovered.

Required:

```text
daily backup
pre-migration backup
pre-release backup
manual backup
```

## SAFE-002 Restore Verification

Test:

```text
backup
 ↓
restore isolated DB
 ↓
integrity check
 ↓
start application
 ↓
smoke tests
```

## SAFE-003 Staging Configuration

Provide production-like configuration without production credentials.

## SAFE-004 Rollback

Document:

```text
application rollback
database rollback
migration rollback
configuration rollback
asset rollback
external service rollback
```

---

# 14. PHASE 5 — ACTIVE USER DATA PROTECTION

Existing users must retain:

```text
user ID
email
phone
profile
applications
application history
status
domain
joining date
enrollment
payments
payment evidence
course progress
tasks
attendance
mentor assignment
projects
submissions
certificates
messages
notifications
referrals
```

Never silently discard data.

Before any migration create:

```text
DATA_INCONSISTENCIES.csv
```

Report inconsistencies instead of silently repairing them.

---

# 15. PHASE 6 — APPLICATION STATE MACHINE

The current portal already has an application lifecycle.

Do not replace status values blindly.

First inventory actual values.

Then implement:

```text
services/application_service.py
```

with a central transition function:

```python
transition_application(
    application_id,
    target_status,
    actor,
    reason,
    request_id
)
```

It must validate:

```text
current state
target state
allowed transition
actor permission
ownership
business conditions
```

Create:

```text
application_status_history
```

with:

```text
id
application_id
old_status
new_status
changed_by
changed_at
reason
request_id
metadata
```

Search the entire codebase for direct status mutation and replace business-critical paths with the transition service.

Tests:

```text
valid transition
invalid transition
unauthorized transition
duplicate request
concurrent request
stale UI request
repeated API request
```

---

# 16. PHASE 7 — ENROLLMENT STATE MACHINE

Separate:

```text
application status
```

from:

```text
enrollment status
```

Document actual current values before introducing new ones.

Implement central transitions.

Prevent impossible combinations unless explicitly supported.

Test:

```text
duplicate enrollment
refresh
multiple tabs
multiple devices
network timeout
retry
stale request
```

---

# 17. PHASE 8 — PAYMENT ARCHITECTURE

The existing manual UPI/payment workflow must continue working.

Add Razorpay without breaking manual fallback.

## Required architecture

```text
product
 ↓
server determines canonical price
 ↓
internal payment record
 ↓
Razorpay order
 ↓
checkout
 ↓
signature verification
 ↓
atomic business transition
 ↓
webhook reconciliation
```

The client must NEVER determine the payable amount.

Required environment variables:

```text
RAZORPAY_KEY_ID
RAZORPAY_KEY_SECRET
RAZORPAY_WEBHOOK_SECRET
```

Never hardcode secrets.

## Required endpoints

```text
POST /api/payment/razorpay/create-order
POST /api/payment/razorpay/verify-payment
POST /api/payment/razorpay/webhook
```

## Signature verification

Use HMAC SHA256 on the server.

Never trust a browser success response without verification.

## Webhooks

Support at minimum:

```text
payment.captured
payment.failed
refund.processed
```

Webhook processing must be idempotent.

Use event IDs/payment IDs to prevent double credit.

## Feature fallback

If Razorpay is not configured:

```text
manual UPI workflow remains available
```

If Razorpay is configured:

```text
Razorpay checkout becomes the primary automated method
```

Do not delete manual fallback until verified and explicitly approved.

---

# 18. PHASE 9 — DATABASE INTEGRITY ENGINE

Create:

```text
scripts/check_data_integrity.py
```

Detect:

```text
orphan users
orphan applications
orphan enrollments
orphan payments
duplicate active applications
duplicate enrollments
impossible states
missing references
invalid certificates
invalid assignments
payment inconsistencies
```

Run:

```text
before release
after migration
after restore
on demand
```

CI should be able to execute it against a test database.

---

# 19. PHASE 10 — AUTHENTICATION REGRESSION

Automate:

```text
signup
login
logout
forgot password
reset password
expired reset token
used reset token
duplicate email
duplicate phone
session expiry
deep links
back button
multiple tabs
multiple devices
admin login
mentor login
company login
intern login
```

Critical journey:

```text
login
 ↓
portal
 ↓
logout
 ↓
browser back
 ↓
portal
```

Expected:

```text
authenticated access denied
```

---

# 20. PHASE 11 — AUTHORIZATION / IDOR

Create:

```text
docs/ROLE_PERMISSION_MATRIX.md
```

Roles should be based on actual repository roles.

For every protected endpoint verify:

```text
authentication
role
ownership
special permission
```

Test cross-user access for:

```text
applications
CV
payments
certificates
messages
tasks
submissions
profiles
learning data
mentor data
company data
```

User A must not access User B's private records.

---

# 21. PHASE 12 — GOLDEN APPLICANT JOURNEY

Automate:

```text
visitor
 ↓
signup
 ↓
application
 ↓
login
 ↓
portal
 ↓
admin review
 ↓
selection
 ↓
candidate sees selection
 ↓
enrollment
 ↓
payment
 ↓
payment acceptance
 ↓
course access
 ↓
task
 ↓
submission
 ↓
completion
 ↓
certificate
```

This is a P0 release gate.

If this fails:

```text
PRODUCTION RELEASE = BLOCKED
```

---

# 22. PHASE 13 — MARKETPLACE

Verify:

```text
company registration
company verification
company approval
company suspension
create listing
draft
publish
expire
close
candidate application
shortlist
interview
selection
hire
```

All counts must come from live database state.

Never hardcode claims such as:

```text
120+ openings
95+ openings
```

if those numbers represent current inventory.

Expired listings must not show active application CTAs.

---

# 23. PHASE 14 — EMAIL / EVENT OUTBOX

Business transactions must not fail merely because email fails.

Prefer:

```text
DB transaction
 ↓
outbox event
 ↓
background worker
 ↓
email
```

Events:

```text
application.submitted
application.selected
application.rejected
enrollment.created
payment.submitted
payment.accepted
payment.rejected
mentor.assigned
task.assigned
task.reviewed
certificate.issued
```

Notification states:

```text
PENDING
SENT
FAILED
RETRYING
DEAD_LETTER
```

---

# 24. PHASE 15 — FILE SECURITY

Audit:

```text
CV
payment screenshot
profile image
certificate
project submission
company documents
```

Validate:

```text
extension
MIME
magic bytes
size
filename
storage
authorization
download permission
```

Test malicious uploads and path traversal.

Private files must never be accessible through predictable public URLs.

---

# 25. PHASE 16 — PRIVACY

Classify fields:

```text
PUBLIC
PRIVATE
ADMIN_ONLY
SENSITIVE
```

Never serialize an entire database/user object into a public API response.

Test:

```text
anonymous
other intern
mentor
company
admin
```

against private endpoints.

---

# 26. PHASE 17 — UX DEAD-END AUDIT

Every user-facing page must answer:

```text
Where am I?
What can I do?
What happens next?
```

Errors must explain:

```text
what happened
why
what the user can do
```

Detect:

```text
404
401
403
500
redirect loops
dead buttons
broken forms
missing assets
JavaScript exceptions
failed API requests
infinite loading
```

---

# 27. PHASE 18 — MOBILE / ACCESSIBILITY

Test:

```text
360x800
390x844
412x915
768x1024
1366x768
1920x1080
```

Critical workflows:

```text
signup
login
portal
courses
tasks
applications
payment
admin
company
```

Accessibility:

```text
keyboard navigation
focus
contrast
labels
ARIA
modals
escape
focus trapping
form errors
```

---

# 28. PHASE 19 — PERFORMANCE

Measure:

```text
TTFB
page load
API latency
DB query time
template rendering
JS execution
image size
```

Find:

```text
N+1 queries
unbounded queries
large joins
large responses
slow external APIs
```

Paginate large admin datasets.

Do not optimize by guesswork. Record measurements before and after.

---

# 29. PHASE 20 — SECURITY REGRESSION

Automate checks for:

```text
CSRF
XSS
SQL injection
IDOR
broken access control
file upload attacks
session fixation
session reuse
rate limit bypass
password reset abuse
private data exposure
secret leakage
```

Never weaken security controls to make tests pass.

---

# 30. PHASE 21 — OBSERVABILITY

Every request should have a request ID.

Where practical propagate it through:

```text
DB audit
email
notification
AI request
exception
payment
learning event
```

Track:

```text
5xx
4xx
latency
DB failures
email failures
payment failures
AI failures
login failures
upload failures
learning failures
```

Provide:

```text
/health
/ready
```

where appropriate.

---

# 31. PHASE 22 — GUIDED LEARNING 2.0

This is a major product subsystem.

Do NOT simply improve the tutor prompt.

The target architecture is:

```text
Assess
 ↓
Understand learner
 ↓
Select concept
 ↓
Teach
 ↓
Check understanding
 ↓
Capture evidence
 ↓
Evaluate
 ↓
Detect misconception
 ↓
Update mastery
 ↓
Select next action
 ↓
Practice
 ↓
Mastery check
 ↓
Schedule review
 ↓
Repeat
```

The learner model must be student-specific.

---

# 32. GUIDED LEARNING — REQUIRED CONCEPT MODEL

Create a controlled hierarchy:

```text
domain
subject
module
topic
concept
sub-concept
skill
```

Each concept should support:

```text
concept_id
name
description
difficulty
prerequisites
learning objectives
assessment criteria
common misconceptions
resources
```

Do not scatter arbitrary concept strings throughout the application.

---

# 33. GUIDED LEARNING — STUDENT MODEL

The authoritative learning state must be scoped to:

```text
student_id + concept_id
```

It should support:

```text
mastery
confidence
evidence
attempt history
last interaction
last review
next review
difficulty
learning velocity
misconceptions
```

Do not infer:

```text
module completed = concept mastered
```

Use:

```text
content completion
+
assessment evidence
+
task evidence
+
learning history
```

---

# 34. GUIDED LEARNING — LEARNING EVENTS

Create durable learning events such as:

```text
diagnostic_started
concept_started
explanation_viewed
question_presented
answer_submitted
answer_evaluated
misconception_detected
mastery_updated
practice_completed
review_scheduled
review_completed
session_started
session_resumed
mentor_escalation
```

Each event should include enough information for audit/replay without storing unnecessary sensitive content.

---

# 35. GUIDED LEARNING — EVALUATOR

Do not use simple keyword matching as the authoritative evaluator for open-ended responses.

Evaluation should produce structured output:

```text
correctness
partial correctness
reasoning quality
concept understanding
misconception
confidence
evidence strength
```

LLM output must be schema-validated.

Invalid evaluator output must use deterministic fallback behavior.

---

# 36. GUIDED LEARNING — MASTERY POLICY

Mastery must be deterministic at the policy layer.

The LLM may provide evidence.

The policy decides mastery.

Conceptually:

```text
evidence
 ↓
validated evaluation
 ↓
mastery policy
 ↓
mastery state
```

Do not allow arbitrary LLM prose to directly set mastery.

---

# 37. GUIDED LEARNING — ADAPTIVE NEXT ACTION

The policy must consider:

```text
mastery
confidence
recent performance
prerequisites
misconceptions
difficulty
time since review
learning velocity
attempt history
assessment evidence
review urgency
session context
```

Possible actions:

```text
EXPLAIN
SIMPLIFY
GIVE_EXAMPLE
ASK_GUIDED_QUESTION
PRACTICE
REMEDIATE
RETEST
REVIEW
ADVANCE
ESCALATE_TO_MENTOR
```

The selection must be deterministic and testable.

---

# 38. GUIDED LEARNING — SPACED REVIEW

Differentiate:

```text
NEW
REINFORCEMENT
REVIEW
REMEDIATION
MASTERY_VALIDATION
```

A recently mastered concept and an old concept must not receive identical review scheduling.

---

# 39. GUIDED LEARNING — SESSION RESUME

A learner must be able to leave and return.

Persist enough state to resume:

```text
current concept
current learning action
session ID
last completed event
pending assessment
mastery state
review state
```

A browser refresh must not duplicate a learning event.

---

# 40. GUIDED LEARNING — STREAMING SAFETY

Streaming responses must not partially mutate authoritative learner state.

Required lifecycle:

```text
response generated
 ↓
evidence captured
 ↓
evaluation completed
 ↓
learning event committed
 ↓
mastery recalculated
 ↓
next action selected
```

Use idempotency keys where required.

Test concurrent submissions.

---

# 41. GUIDED LEARNING — RAG

If retrieval is used:

```text
student question
 ↓
concept/context selection
 ↓
retrieval
 ↓
grounded context
 ↓
LLM generation
 ↓
structured evaluation
```

The tutor must not invent curriculum facts when authoritative content exists.

Track retrieval failures.

Use deterministic curriculum fallback.

---

# 42. GUIDED LEARNING — ADAPTIVE UI

The UI should visibly communicate:

```text
current objective
current concept
why this activity is being shown
what the learner should do
feedback
progress
next action
```

Do not expose raw internal model scores in confusing ways.

The learner should understand why the tutor is changing difficulty or asking for remediation.

---

# 43. GUIDED LEARNING — MENTOR/ADMIN VIEW

Mentors/admins should eventually see:

```text
concept mastery
weak concepts
misconceptions
confidence
recent evidence
review due
learning velocity
struggle indicators
mentor escalation
```

Do not expose unnecessary private conversation content.

---

# 44. GUIDED LEARNING — SYNTHETIC LEARNER TESTING

Create synthetic learners representing:

```text
fast learner
slow learner
high confidence / low mastery
low confidence / high mastery
repeated misconception
random guessing
partial understanding
strong conceptual understanding
session interruption
concurrent session
```

Run the same learning journey against each.

Verify the adaptive policy behaves differently where expected.

---

# 45. GUIDED LEARNING — GOLDEN JOURNEY

Automate:

```text
student enters module
 ↓
diagnostic
 ↓
initial concept
 ↓
explanation
 ↓
question
 ↓
answer
 ↓
evaluation
 ↓
mastery update
 ↓
adaptive recommendation
 ↓
practice
 ↓
misconception
 ↓
remediation
 ↓
retest
 ↓
mastery gate
 ↓
next concept
 ↓
review scheduling
 ↓
session resume
```

This must be deterministic at the policy layer even though tutor language is generated.

---

# 46. GUIDED LEARNING — FEATURE FLAG

Implement:

```text
GUIDED_LEARNING_V2=false
```

Old Guided Learning must remain usable until V2 has passed its stability window.

Do not delete the old learning path during initial V2 implementation.

---

# 47. GUIDED LEARNING — MIGRATION

Before migration:

```text
student_learning_migration_report
```

For every active learner:

```text
old progress
concept mapping
mastery initialization
unmapped concepts
potential issues
```

No learner may lose progress.

---

# 48. GUIDED LEARNING TASK IDS

Use:

```text
GL-INV-001
GL-DATA-001
GL-CONCEPT-001
GL-MASTERY-001
GL-EVAL-001
GL-MISCONCEPTION-001
GL-ADAPT-001
GL-REVIEW-001
GL-RAG-001
GL-SESSION-001
GL-CONCURRENCY-001
GL-UI-001
GL-METRICS-001
GL-MIGRATION-001
GL-ROLLOUT-001
GL-QA-001
```

---

# 49. GUIDED LEARNING IMPLEMENTATION ORDER

Strict order:

```text
1. Audit current Guided Learning
2. Characterization tests
3. Concept model
4. Prerequisite graph
5. Learning objectives
6. Student mastery model
7. Learning events
8. Evidence pipeline
9. Deterministic mastery policy
10. Structured evaluator
11. Misconception tracking
12. Adaptive next-action engine
13. Spaced review
14. Session persistence
15. RAG-aware tutor
16. Adaptive UI
17. Mentor/admin analytics
18. Synthetic learner simulator
19. Benchmark against existing tutor
20. Feature flag
21. Active learner migration
22. Monitoring
23. Gradual rollout
```

Do not reverse the order without recording a dependency decision.

---

# 50. PHASE 23 — MONOLITH MODULARIZATION

Do NOT rewrite the application.

Extract gradually:

```text
services/
├── auth_service.py
├── application_service.py
├── enrollment_service.py
├── payment_service.py
├── notification_service.py
├── certificate_service.py
├── marketplace_service.py
├── learning_service.py
├── mastery_service.py
└── interview_service.py
```

Routes:

```text
routes/
├── auth.py
├── applications.py
├── enrollment.py
├── payment.py
├── marketplace.py
├── admin.py
├── mentor.py
├── company.py
├── intern.py
└── learning.py
```

Every extraction must preserve existing behavior.

Before refactor:

```text
characterization test
```

After refactor:

```text
same tests
+
new tests
```

---

# 51. PHASE 24 — DATABASE ABSTRACTION

Do not migrate to PostgreSQL immediately.

First remove unnecessary SQLite-specific assumptions from business logic.

Business services should depend on repository/service interfaces where practical.

---

# 52. PHASE 25 — POSTGRESQL PREPARATION

Only after workflow stabilization:

```text
SQLite
 ↓
schema compatibility
 ↓
PostgreSQL staging
 ↓
data migration
 ↓
comparison
 ↓
integrity check
 ↓
rollback test
```

Production migration is OUT OF SCOPE until all earlier gates pass.

---

# 53. PHASE 26 — DATA INTEGRITY DASHBOARD

Eventually provide admin visibility for:

```text
users
applications
enrollments
payments
active interns
completed interns
certificates
```

Integrity:

```text
orphan applications
orphan enrollments
duplicate active applications
impossible states
expired live listings
failed critical jobs
```

---

# 54. PHASE 27 — RELEASE PROCESS

Every release requires:

## Backend

```text
unit tests
integration tests
database tests
security tests
```

## Frontend

```text
Playwright
mobile
desktop
responsive
console errors
```

## Business

```text
signup
application
selection
enrollment
payment
learning
task
certificate
```

## Infrastructure

```text
backup
restore
health
rollback
```

---

# 55. PRODUCTION CANARY

The local agent must NOT perform production deployment automatically.

It may prepare release artifacts and instructions.

Preferred:

```text
local
 ↓
tests
 ↓
commit
 ↓
GitHub
 ↓
CI
 ↓
staging
 ↓
human-controlled production deployment
```

---

# 56. GIT COMMIT POLICY

Commit small verified units.

Examples:

```text
chore: establish verified baseline
docs: add route inventory
test: add application transition tests
feat: add application state transition service
feat: add payment gateway abstraction
feat: add razorpay order verification
feat: add learning concept model
feat: add mastery policy
test: add golden applicant journey
feat: add guided learning adaptive policy
```

Never create giant commits containing unrelated changes.

---

# 57. PUSH POLICY

Before every push:

```bash
git status
git diff --check
pytest
git diff
git log --oneline -5
git remote -v
```

Then push ONLY to:

```text
origin → Internshipportal4
```

Verify:

```bash
git remote -v
```

before pushing.

Never push if origin points to the production/source repository.

After push:

```bash
git fetch origin
git status
git log --oneline -5
```

Record the pushed commit SHA in:

```text
.agent/SESSION_LOG.md
```

---

# 58. CI REQUIREMENTS

Create GitHub Actions where practical.

CI should run:

```text
syntax validation
unit tests
integration tests
security checks
secret scan
database integrity tests
frontend tests
Playwright
build checks
```

A failed critical test must prevent the workflow from being marked successful.

---

# 59. BUG HANDLING

When discovering a bug:

1. Record it.
2. Assign P0–P4.
3. Reproduce it.
4. Identify affected users.
5. Add regression test.
6. Fix smallest safe scope.
7. Run affected tests.
8. Run regression suite.
9. Document fix.

Severity:

```text
P0 production blocker/data loss/security
P1 major workflow failure
P2 significant defect
P3 minor defect
P4 cosmetic
```

---

# 60. LEGACY CODE

Never delete code merely because it looks unused.

Classify:

```text
ACTIVE
LEGACY
DUPLICATE
UNUSED
UNKNOWN
```

Removal requires:

```text
usage analysis
 ↓
test
 ↓
staging
 ↓
approval
 ↓
removal
```

---

# 61. DATA INCONSISTENCY

Never silently repair production data.

Required process:

```text
detect
 ↓
report
 ↓
classify
 ↓
define correction rule
 ↓
dry run
 ↓
backup
 ↓
apply
 ↓
verify
```

---

# 62. TEST FAILURE RULE

Never weaken a test just to make CI green.

Classify failure:

```text
implementation bug
test bug
environment problem
expected behavior change
data problem
dependency failure
```

Record the decision.

---

# 63. PHASE GATES

## Gate 0

Inventory complete.

## Gate 1

Local baseline runs.

## Gate 2

Backup/restore/staging/rollback tooling verified.

## Gate 3

Application state machine verified.

## Gate 4

Enrollment state machine verified.

## Gate 5

Payment workflow and Razorpay verification tested.

## Gate 6

Database integrity checker passes.

## Gate 7

Authentication and authorization tests pass.

## Gate 8

Golden Applicant Journey passes.

## Gate 9

Marketplace passes.

## Gate 10

Email/event reliability passes.

## Gate 11

Security/privacy passes.

## Gate 12

UX/mobile/accessibility passes.

## Gate 13

Performance baseline established.

## Gate 14

Guided Learning V2 characterization tests pass.

## Gate 15

Guided Learning V2 policy/evaluator/mastery tests pass.

## Gate 16

Guided Learning V2 synthetic learner suite passes.

## Gate 17

Guided Learning V2 feature-flag rollback passes.

## Gate 18

PostgreSQL staging migration passes.

## Gate 19

Final UAT passes.

Only then prepare a production release.

---

# 64. RELEASE BLOCKERS

Never release if any of the following exist:

```text
data loss
authentication bypass
authorization bypass
payment inconsistency
duplicate financial credit
broken application lifecycle
broken enrollment lifecycle
private data exposure
Golden Applicant Journey failure
database migration failure
backup failure
rollback failure
critical 500
critical security vulnerability
Guided Learning V2 learner-data corruption
Guided Learning V2 nondeterministic state mutation
```

---

# 65. DEFINITION OF DONE

A task is complete only when:

```text
CODE
+
TEST
+
TEST PASS
+
SECURITY REVIEW
+
DATA/MIGRATION REVIEW
+
DOCUMENTATION
+
ROLLBACK CONSIDERATION
+
GIT COMMIT
```

A task is not `RELEASED` until pushed to `Internshipportal4`.

---

# 66. REQUIRED AGENT TRACKING

## `.agent/CURRENT_PHASE.md`

```markdown
# Current Phase

Phase: 0
Name: Verified System Inventory
Status: IN_PROGRESS

Current Task:
INV-001

Completed:
- None

In Progress:
- INV-001

Blocked:
- None

Next:
- INV-002

Last Verified:
YYYY-MM-DD HH:MM

Last Test Result:
N/A

Last Commit:
N/A
```

## `.agent/TASK_QUEUE.md`

Maintain P0/P1/P2/P3 tasks.

Every task must have:

```text
ID
description
priority
status
dependencies
files
tests
verification
commit
```

## `.agent/COMPLETED.md`

Record:

```text
task ID
date
implementation
tests
files
security impact
migration impact
verification
commit SHA
```

## `.agent/BLOCKED.md`

Record:

```text
task
reason
dependency
required action
workaround
date
```

## `.agent/DECISIONS.md`

Record:

```text
decision ID
date
decision
reason
alternatives
impact
migration impact
rollback
```

## `.agent/SESSION_LOG.md`

Record:

```text
session
phase
tasks
work completed
tests
failures
files changed
decisions
remaining work
next session
commit SHA
push status
```

---

# 67. INITIAL TASK QUEUE

## P0

```text
[ ] INV-001 Verify source repository
[ ] INV-002 Verify target repository
[ ] INV-003 Create preflight report
[ ] INV-004 Inventory routes
[ ] INV-005 Inventory features
[ ] INV-006 Inventory database
[ ] INV-007 Inventory external services
[ ] SAFE-001 Verify local environment safety
[ ] SAFE-002 Establish baseline tests
[ ] SAFE-003 Import source safely into Internshipportal4
[ ] SAFE-004 Verify local startup
[ ] APP-001 Application state inventory
[ ] APP-002 Characterization tests
[ ] DB-001 Data integrity checker
[ ] E2E-001 Golden Applicant Journey
```

## P1

```text
[ ] APP-003 Application transition service
[ ] APP-004 Application history
[ ] ENR-001 Enrollment transition service
[ ] PAY-001 Payment abstraction
[ ] PAY-002 Razorpay order creation
[ ] PAY-003 Razorpay signature verification
[ ] PAY-004 Razorpay webhook
[ ] PAY-005 Payment idempotency
[ ] AUTH-001 Authorization matrix
[ ] AUTH-002 IDOR suite
[ ] FILE-001 File security audit
[ ] EMAIL-001 Outbox architecture
```

## P2

```text
[ ] GL-INV-001 Guided Learning audit
[ ] GL-DATA-001 Concept data model
[ ] GL-CONCEPT-001 Concept graph
[ ] GL-MASTERY-001 Mastery model
[ ] GL-EVAL-001 Structured evaluator
[ ] GL-MISCONCEPTION-001 Misconception model
[ ] GL-ADAPT-001 Adaptive policy
[ ] GL-REVIEW-001 Spaced review
[ ] GL-SESSION-001 Session persistence
[ ] GL-RAG-001 RAG grounding
[ ] GL-UI-001 Adaptive UI
[ ] GL-QA-001 Synthetic learner testing
```

---

# 68. FIRST IMPLEMENTATION SESSION — EXACT EXPECTED BEHAVIOR

Do NOT immediately start modifying business logic.

The first session must:

1. Clone source.
2. Clone target.
3. Verify target state.
4. Verify remotes.
5. Verify branches.
6. Inspect repository structure.
7. Read existing agent/development documentation.
8. Run baseline tests.
9. Run local startup.
10. Generate inventories.
11. Create `.agent/` tracking.
12. Create `docs/PROJECT_STATE.md`.
13. Record baseline commit SHA.
14. Import source only if target is empty.
15. Commit the clean baseline.
16. Push baseline to `Internshipportal4`.
17. Verify remote commit.
18. Stop and update `.agent/CURRENT_PHASE.md`.

Do not implement Razorpay, state machines, Guided Learning V2, PostgreSQL, or large refactors in the first session.

---

# 69. CRITICAL RULE ABOUT GITHUB

The agent must treat GitHub as a version-control destination, NOT as the development environment.

Development happens:

```text
LOCAL
```

GitHub is updated only after:

```text
implementation
+
tests
+
verification
+
commit
```

Every pushed change must be reproducible from the local repository.

---

# 70. FINAL TARGET ARCHITECTURE

The desired evolution is:

```text
                    DBERT INTERNSHIP PLATFORM
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
          ▼                   ▼                   ▼
      AUTH/USERS        APPLICATIONS          MARKETPLACE
          │                   │                   │
          │                   ▼                   │
          │             STATE MACHINE            │
          │                   │                   │
          └──────────────┬────┴──────────────┬────┘
                         ▼                   ▼
                    ENROLLMENT            PAYMENT
                         │                   │
                         ▼                   ▼
                       LMS             PAYMENT EVENTS
                         │
                         ▼
                 GUIDED LEARNING 2.0
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
          CONCEPTS    MASTERY    EVIDENCE
              │          │          │
              └──────────┼──────────┘
                         ▼
                  ADAPTIVE POLICY
                         │
                         ▼
                       TUTOR
                         │
                         ▼
                  PRACTICE/REVIEW
                         │
                         ▼
                     MASTERY
```

The key principle is:

```text
DO NOT BUILD A CHATBOT + PROGRESS BAR.

BUILD:

Evidence
→ Learner Model
→ Deterministic Decision
→ Teaching
→ Practice
→ Assessment
→ Mastery
→ Retention
→ New Evidence
```

---

# 71. FINAL INSTRUCTION TO THE LOCAL AI AGENT

You are not authorized to declare the project complete because code was generated.

You must leave a verifiable trail:

```text
PLAN
 ↓
IMPLEMENT
 ↓
TEST
 ↓
VERIFY
 ↓
DOCUMENT
 ↓
COMMIT
 ↓
PUSH
```

If something is unknown:

```text
INVESTIGATE
```

If something is broken:

```text
REPRODUCE
```

If data is inconsistent:

```text
REPORT
```

If a migration is unsafe:

```text
STOP
```

If a test fails:

```text
INVESTIGATE
```

If a session ends:

```text
UPDATE .agent/
```

If you cannot verify a change:

```text
DO NOT MARK VERIFIED
```

The final repository must be:

```text
locally reproducible
testable
auditable
secure
migration-safe
rollback-capable
Git-tracked
and suitable for controlled deployment
```

Target repository:

```text
https://github.com/ainabhinavsharma/Internshipportal4
```

Source/reference repository:

```text
https://github.com/ainabhinavsharma/Internshipportal
```
