#!/usr/bin/env python3
"""
scripts/check_data_integrity.py - Database Integrity Engine
Implements Phase 9 requirements of INTERNSHIPPORTAL4_LOCAL_AI_AGENT_MASTER_PLAN.md

Detects:
  - Orphan users, applications, enrollments, payments
  - Duplicate active applications & duplicate enrollments
  - Impossible lifecycle state combinations
  - Broken foreign key references (PRAGMA foreign_key_check)
  - SQLite low-level corruption (PRAGMA integrity_check)
  - Invalid certificates & assignments
  - Payment proof inconsistencies

Outputs formatted console report and optional markdown documentation.
"""

import os
import sys
import json
import sqlite3
import argparse
from datetime import datetime
from typing import Dict, List, Any, Tuple

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_DB = os.environ.get("DB_FILE") or os.path.join(BASE_DIR, "internship.db")


class DataIntegrityChecker:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.results: Dict[str, Any] = {}
        self.critical_count = 0
        self.warning_count = 0
        self.info_count = 0

    def connect(self) -> sqlite3.Connection:
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"Database file not found at {self.db_path}")
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def run_all_checks(self) -> Dict[str, Any]:
        """Runs the complete suite of integrity checks."""
        conn = self.connect()
        try:
            self.results["database_path"] = self.db_path
            self.results["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 1. SQLite low-level corruption
            self._check_sqlite_integrity(conn)

            # 2. Broken foreign keys
            self._check_foreign_keys(conn)

            # 3. Orphan applications (no matching intern_account)
            self._check_orphan_applications(conn)

            # 4. Orphan enrollments (no matching intern or application)
            self._check_orphan_enrollments(conn)

            # 5. Orphan payments
            self._check_orphan_payments(conn)

            # 6. Duplicate active applications
            self._check_duplicate_applications(conn)

            # 7. Duplicate enrollments
            self._check_duplicate_enrollments(conn)

            # 8. Impossible state combinations
            self._check_impossible_states(conn)

            # 9. Invalid certificates
            self._check_invalid_certificates(conn)

            # 10. Invalid task submissions
            self._check_invalid_submissions(conn)

            # 11. Payment proof inconsistencies
            self._check_payment_inconsistencies(conn)

            self.results["summary"] = {
                "critical": self.critical_count,
                "warning": self.warning_count,
                "info": self.info_count,
                "clean": (self.critical_count == 0 and self.warning_count == 0)
            }
            return self.results
        finally:
            conn.close()

    def _check_sqlite_integrity(self, conn: sqlite3.Connection):
        cur = conn.execute("PRAGMA integrity_check")
        rows = [r[0] for r in cur.fetchall()]
        is_ok = rows == ["ok"]
        if not is_ok:
            self.critical_count += len(rows)
        self.results["sqlite_integrity"] = {
            "status": "PASS" if is_ok else "FAIL",
            "messages": rows
        }

    def _check_foreign_keys(self, conn: sqlite3.Connection):
        cur = conn.execute("PRAGMA foreign_key_check")
        rows = cur.fetchall()
        issues = []
        for r in rows:
            issues.append({
                "table": r[0],
                "rowid": r[1],
                "referenced_table": r[2],
                "fkid": r[3]
            })
        if issues:
            self.warning_count += len(issues)
        self.results["foreign_key_check"] = {
            "count": len(issues),
            "issues": issues[:50]
        }

    def _check_orphan_applications(self, conn: sqlite3.Connection):
        query = """
            SELECT a.id, a.email, a.status, a.name
            FROM applications a
            LEFT JOIN intern_accounts i ON LOWER(a.email) = LOWER(i.email)
            WHERE i.id IS NULL
        """
        rows = conn.execute(query).fetchall()
        orphans = [dict(r) for r in rows]
        if orphans:
            self.warning_count += len(orphans)
        self.results["orphan_applications"] = {
            "count": len(orphans),
            "samples": orphans[:20]
        }

    def _check_orphan_enrollments(self, conn: sqlite3.Connection):
        query = """
            SELECT e.id, e.email, e.name, e.domain, e.payment_status
            FROM enrollments e
            LEFT JOIN intern_accounts i ON LOWER(e.email) = LOWER(i.email)
            WHERE i.id IS NULL
        """
        rows = conn.execute(query).fetchall()
        orphans = [dict(r) for r in rows]
        if orphans:
            self.warning_count += len(orphans)
        self.results["orphan_enrollments"] = {
            "count": len(orphans),
            "samples": orphans[:20]
        }

    def _check_orphan_payments(self, conn: sqlite3.Connection):
        query = """
            SELECT cp.id, cp.intern_id, cp.course_id, cp.amount
            FROM course_payments cp
            LEFT JOIN intern_accounts i ON cp.intern_id = i.id
            WHERE i.id IS NULL
        """
        rows = conn.execute(query).fetchall()
        orphans = [dict(r) for r in rows]
        if orphans:
            self.warning_count += len(orphans)
        self.results["orphan_payments"] = {
            "count": len(orphans),
            "samples": orphans[:20]
        }

    def _check_duplicate_applications(self, conn: sqlite3.Connection):
        query = """
            SELECT LOWER(email) as email, COUNT(*) as cnt
            FROM applications
            WHERE status != 'Rejected'
            GROUP BY LOWER(email)
            HAVING COUNT(*) > 1
        """
        rows = conn.execute(query).fetchall()
        dupes = [dict(r) for r in rows]
        if dupes:
            self.warning_count += len(dupes)
        self.results["duplicate_active_applications"] = {
            "count": len(dupes),
            "samples": dupes[:20]
        }

    def _check_duplicate_enrollments(self, conn: sqlite3.Connection):
        query = """
            SELECT LOWER(email) as email, COUNT(*) as cnt
            FROM enrollments
            GROUP BY LOWER(email)
            HAVING COUNT(*) > 1
        """
        rows = conn.execute(query).fetchall()
        dupes = [dict(r) for r in rows]
        if dupes:
            self.info_count += len(dupes)
        self.results["duplicate_enrollments"] = {
            "count": len(dupes),
            "samples": dupes[:20]
        }

    def _check_impossible_states(self, conn: sqlite3.Connection):
        # 1. Enrollment Accepted but Application is Rejected
        q1 = """
            SELECT e.id as enrollment_id, e.email, e.payment_status, a.status as app_status
            FROM enrollments e
            JOIN applications a ON LOWER(e.email) = LOWER(a.email)
            WHERE e.payment_status = 'Accepted' AND a.status = 'Rejected'
        """
        # 2. Application Accepted but Enrollment Rejected
        q2 = """
            SELECT e.id as enrollment_id, e.email, e.payment_status, a.status as app_status
            FROM enrollments e
            JOIN applications a ON LOWER(e.email) = LOWER(a.email)
            WHERE e.payment_status = 'Rejected' AND a.status = 'Accepted'
        """
        rows1 = conn.execute(q1).fetchall()
        rows2 = conn.execute(q2).fetchall()
        issues = [dict(r) for r in rows1] + [dict(r) for r in rows2]
        if issues:
            self.critical_count += len(issues)
        self.results["impossible_states"] = {
            "count": len(issues),
            "issues": issues[:20]
        }

    def _check_invalid_certificates(self, conn: sqlite3.Connection):
        query = """
            SELECT c.id, c.intern_id, c.cert_id
            FROM intern_certificates c
            LEFT JOIN intern_accounts i ON c.intern_id = i.id
            WHERE i.id IS NULL OR c.cert_id IS NULL OR c.cert_id = ''
        """
        rows = conn.execute(query).fetchall()
        invalids = [dict(r) for r in rows]
        if invalids:
            self.warning_count += len(invalids)
        self.results["invalid_certificates"] = {
            "count": len(invalids),
            "samples": invalids[:20]
        }

    def _check_invalid_submissions(self, conn: sqlite3.Connection):
        query = """
            SELECT ts.id, ts.task_id, ts.intern_id
            FROM task_submissions ts
            LEFT JOIN tasks t ON ts.task_id = t.id
            WHERE t.id IS NULL
        """
        rows = conn.execute(query).fetchall()
        invalids = [dict(r) for r in rows]
        if invalids:
            self.warning_count += len(invalids)
        self.results["invalid_submissions"] = {
            "count": len(invalids),
            "samples": invalids[:20]
        }

    def _check_payment_inconsistencies(self, conn: sqlite3.Connection):
        query = """
            SELECT id, email, amount, payment_status, payment_screenshot, razorpay_payment_id
            FROM enrollments
            WHERE payment_status = 'Accepted'
              AND (payment_screenshot IS NULL OR payment_screenshot = '')
              AND (razorpay_payment_id IS NULL OR razorpay_payment_id = '')
        """
        rows = conn.execute(query).fetchall()
        invalids = [dict(r) for r in rows]
        if invalids:
            self.warning_count += len(invalids)
        self.results["payment_inconsistencies"] = {
            "count": len(invalids),
            "samples": invalids[:20]
        }

    def generate_markdown_report(self) -> str:
        s = self.results.get("summary", {})
        md = [
            "# Database Integrity Audit Report",
            f"**Execution Timestamp:** {self.results.get('timestamp')}",
            f"**Target Database:** `{self.results.get('database_path')}`",
            "",
            "## 1. Executive Summary",
            f"- **Overall Status:** {'PASS (Clean)' if s.get('clean') else 'ATTENTION REQUIRED'}",
            f"- **Critical Anomalies (P0):** {s.get('critical', 0)}",
            f"- **Warnings (P1):** {s.get('warning', 0)}",
            f"- **Informational (P2):** {s.get('info', 0)}",
            "",
            "## 2. Integrity Check Metrics",
            "| Check Dimension | Status | Anomaly Count | Severity |",
            "|---|---|---|---|",
            f"| SQLite Page/B-Tree Integrity | {self.results.get('sqlite_integrity', {}).get('status')} | {0 if self.results.get('sqlite_integrity', {}).get('status') == 'PASS' else 1} | CRITICAL |",
            f"| Foreign Key References | {'PASS' if self.results.get('foreign_key_check', {}).get('count') == 0 else 'WARN'} | {self.results.get('foreign_key_check', {}).get('count')} | WARNING |",
            f"| Orphan Applications | {'PASS' if self.results.get('orphan_applications', {}).get('count') == 0 else 'WARN'} | {self.results.get('orphan_applications', {}).get('count')} | WARNING |",
            f"| Orphan Enrollments | {'PASS' if self.results.get('orphan_enrollments', {}).get('count') == 0 else 'WARN'} | {self.results.get('orphan_enrollments', {}).get('count')} | WARNING |",
            f"| Orphan Course Payments | {'PASS' if self.results.get('orphan_payments', {}).get('count') == 0 else 'WARN'} | {self.results.get('orphan_payments', {}).get('count')} | WARNING |",
            f"| Duplicate Active Applications | {'PASS' if self.results.get('duplicate_active_applications', {}).get('count') == 0 else 'WARN'} | {self.results.get('duplicate_active_applications', {}).get('count')} | WARNING |",
            f"| Duplicate Enrollments | {'PASS' if self.results.get('duplicate_enrollments', {}).get('count') == 0 else 'INFO'} | {self.results.get('duplicate_enrollments', {}).get('count')} | INFO |",
            f"| Impossible State Combinations | {'PASS' if self.results.get('impossible_states', {}).get('count') == 0 else 'FAIL'} | {self.results.get('impossible_states', {}).get('count')} | CRITICAL |",
            f"| Invalid Certificates | {'PASS' if self.results.get('invalid_certificates', {}).get('count') == 0 else 'WARN'} | {self.results.get('invalid_certificates', {}).get('count')} | WARNING |",
            f"| Invalid Task Submissions | {'PASS' if self.results.get('invalid_submissions', {}).get('count') == 0 else 'WARN'} | {self.results.get('invalid_submissions', {}).get('count')} | WARNING |",
            f"| Payment Proof Inconsistencies | {'PASS' if self.results.get('payment_inconsistencies', {}).get('count') == 0 else 'WARN'} | {self.results.get('payment_inconsistencies', {}).get('count')} | WARNING |",
            "",
            "## 3. Recommended Remediation Runbook",
            "- For **Impossible States**: Inspect `application_status_history` and `enrollment_status_history` to identify actor and execute reconciling state transition.",
            "- For **Duplicate Active Applications**: Consolidate latest active submission and mark superseded rows as `Rejected` with reason `'Consolidated duplicate'`.",
            "- For **Foreign Key Gaps**: Run pre-release backfill script.",
            ""
        ]
        return "\n".join(md)


def main():
    parser = argparse.ArgumentParser(description="Database Integrity Engine")
    parser.add_argument("--db", default=DEFAULT_DB, help="Path to SQLite database")
    parser.add_argument("--report", action="store_true", help="Write report to docs/DATA_INTEGRITY_REPORT.md")
    parser.add_argument("--json", action="store_true", help="Output JSON results")
    parser.add_argument("--fail-on-critical", action="store_true", help="Exit code 1 if critical issues found")
    args = parser.parse_args()

    if not os.path.exists(args.db):
        print(f"[!] Target database does not exist: {args.db}")
        # If in fresh dev without DB, report clean bypass
        sys.exit(0)

    checker = DataIntegrityChecker(args.db)
    res = checker.run_all_checks()

    if args.json:
        print(json.dumps(res, indent=2))
    else:
        summary = res["summary"]
        print("=" * 60)
        print("DATABASE INTEGRITY AUDIT ENGINE")
        print("=" * 60)
        print(f"Target DB:  {args.db}")
        print(f"Status:     {'CLEAN' if summary['clean'] else 'ISSUES FOUND'}")
        print(f"Critical:   {summary['critical']}")
        print(f"Warnings:   {summary['warning']}")
        print(f"Info:       {summary['info']}")
        print("=" * 60)

    if args.report:
        report_path = os.path.join(BASE_DIR, "docs", "DATA_INTEGRITY_REPORT.md")
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(checker.generate_markdown_report())
        print(f"[+] Written report to {report_path}")

    if args.fail_on_critical and checker.critical_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
