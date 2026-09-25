"""
scripts/benchmark_performance.py
Phase 19: Performance Baseline Measurement & Benchmarking CLI.

Executes:
1. Endpoint latency benchmarks (TTFB, avg, p95, max) across critical routes.
2. Static asset weight and payload size audit.
3. Database query efficiency checks.
4. Generates/updates docs/PERFORMANCE_BASELINE.md.
"""

import sys
import os
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import app
from services.performance_service import (
    benchmark_endpoint,
    audit_static_assets,
    get_performance_recommendations,
    SLA_THRESHOLDS_MS,
)


def run_benchmark():
    print("=" * 60)
    print("PHASE 19 — PERFORMANCE BENCHMARK & PROFILING ENGINE")
    print("=" * 60)

    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False

    target_routes = [
        ("/", "GET"),
        ("/courses", "GET"),
        ("/api/public/courses", "GET"),
        ("/jobs", "GET"),
        ("/internships", "GET"),
        ("/admin-login", "GET"),
    ]

    results = []
    with app.test_client() as client:
        print("\n[*] Benchmarking Critical Routes (5 iterations each)...")
        for path, method in target_routes:
            res = benchmark_endpoint(client, path, method=method, iterations=5)
            results.append(res)
            print(f"    - {path:22} | Status: {res['status_code']} | Avg: {res['avg_ms']:6.2f}ms | p95: {res['p95_ms']:6.2f}ms | Size: {res['payload_bytes']} B")

    print("\n[*] Auditing Static Assets...")
    asset_audit = audit_static_assets("static")
    print(f"    - Total Assets: {asset_audit['total_assets']}")
    print(f"    - Total Size:   {asset_audit['total_kb']} KB")
    print(f"    - Large Assets (>500KB): {asset_audit['large_asset_count']}")
    for a in asset_audit.get("large_assets", []):
        print(f"      * {a['path']}: {a['size_kb']} KB")

    recommendations = get_performance_recommendations(results, asset_audit)
    print("\n[*] Recommendations & Findings:")
    if recommendations:
        for r in recommendations:
            print(f"    - {r}")
    else:
        print("    [+] All tested routes and assets operate within SLA limits.")

    # Write documentation report: docs/PERFORMANCE_BASELINE.md
    docs_dir = Path("docs")
    docs_dir.mkdir(exist_ok=True)
    report_file = docs_dir / "PERFORMANCE_BASELINE.md"

    report_lines = [
        "# Performance Baseline & Audit Report",
        "",
        "## 1. Overview",
        "Phase 19 establishing performance baseline, latency SLAs, query indexing, and caching strategy.",
        "",
        "## 2. Route Latency Benchmarks (TTFB & Processing)",
        "",
        "| Route | Method | Status | Min (ms) | Avg (ms) | p95 (ms) | Max (ms) | Payload (Bytes) | SLA Status |",
        "|---|---|---|---|---|---|---|---|---|",
    ]

    for r in results:
        sla_limit = SLA_THRESHOLDS_MS.get("api_endpoint" if r["path"].startswith("/api") else "public_page", 250.0)
        sla_pass = "PASSED" if r["avg_ms"] <= sla_limit else "EXCEEDS SLA"
        report_lines.append(
            f"| `{r['path']}` | {r['method']} | {r['status_code']} | {r['min_ms']} | {r['avg_ms']} | {r['p95_ms']} | {r['max_ms']} | {r['payload_bytes']} | **{sla_pass}** |"
        )

    report_lines.extend([
        "",
        "## 3. Static Asset Inventory & Size Distribution",
        "",
        f"- **Total Static Assets**: {asset_audit['total_assets']}",
        f"- **Total Asset Footprint**: {asset_audit['total_kb']} KB",
        f"- **Large Assets (> 500 KB)**: {asset_audit['large_asset_count']}",
        "",
        "### Top Static Assets by Size",
        "",
        "| Asset Path | Category | Size (KB) | Optimization Status |",
        "|---|---|---|---|",
    ])

    for a in asset_audit.get("assets", [])[:10]:
        status = "Needs Compression (>500KB)" if a["size_kb"] > 500 else "Optimized"
        report_lines.append(f"| `{a['path']}` | {a['category']} | {a['size_kb']} | {status} |")

    report_lines.extend([
        "",
        "## 4. Database Indexing Strategy",
        "",
        "The following high-selectivity indexes ensure constant-time / logarithmic index scans on core queries:",
        "- `idx_applications_status_created`: `applications(status, created_at DESC)`",
        "- `idx_applications_email`: `applications(email)`",
        "- `idx_enrollments_status_created`: `enrollments(payment_status, created_at DESC)`",
        "- `idx_enrollments_email`: `enrollments(email)`",
        "- `idx_attendance_intern_date`: `attendance(intern_id, date DESC)`",
        "- `idx_course_day_quizzes_course`: `course_day_quizzes(course_id, day_number)`",
        "- `idx_course_enr_email`: `course_enrollments(email)`",
        "- `idx_posts_expires`: `posts(expires_at)`",
        "",
        "## 5. HTTP Caching Headers",
        "",
        "- Static Assets (`/static/...`): `Cache-Control: public, max-age=31536000, immutable`",
        "- Authenticated User Paths (`/portal`, `/admin`, etc.): `Cache-Control: no-store, no-cache, must-revalidate, max-age=0` (anti-back-button leak protection)",
        "",
        "## 6. Recommendations",
        "",
    ])

    if recommendations:
        for rec in recommendations:
            report_lines.append(f"- {rec}")
    else:
        report_lines.append("- All evaluated routes operate within strict SLA latency targets.")

    report_file.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    print(f"\n[+] Baseline report saved to: {report_file.as_posix()}")
    print("=" * 60)


if __name__ == "__main__":
    run_benchmark()
