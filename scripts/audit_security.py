#!/usr/bin/env python3
"""
scripts/audit_security.py - Automated Security & Vulnerability Auditor
DBERT Internship Portal - Phase 20 Security Regression

Executes:
1. Static code analysis using Bandit (AST security linter against app.py and services/).
2. Dependency vulnerability analysis using pip-audit (CVE database scan on requirements.txt).
3. Secret and environment safety verification via verify_env_safety.py.
"""
import os
import sys
import time
import subprocess

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def run_step(step_name, command, cwd=BASE_DIR):
    print(f"\n[*] Running: {step_name}...")
    start_time = time.time()
    try:
        res = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            shell=False
        )
        duration = time.time() - start_time
        if res.returncode == 0:
            print(f"[+] PASS: {step_name} ({duration:.2f}s)")
            return True, duration, res.stdout
        else:
            print(f"[-] FAIL: {step_name} ({duration:.2f}s) - Exit code {res.returncode}")
            output = (res.stdout + "\n" + res.stderr).strip()
            print(f"    Details: {output[:400]}..." if len(output) > 400 else f"    Details: {output}")
            return False, duration, output
    except Exception as e:
        duration = time.time() - start_time
        print(f"[!] ERROR: {step_name} failed to execute: {e}")
        return False, duration, str(e)


def main():
    print("=" * 65)
    print(" DBERT PORTAL AUTOMATED SECURITY AUDIT (PHASE 20)")
    print("=" * 65)

    steps = [
        (
            "Bandit AST Security Linter",
            [sys.executable, "-m", "bandit", "-r", "app.py", "services/", "-c", "bandit.yaml"]
        ),
        (
            "Pip-Audit Dependency CVE Scan",
            [sys.executable, "-m", "pip_audit", "-r", "requirements.txt"]
        ),
        (
            "Tracked Secrets & Database Verifier",
            [sys.executable, os.path.join(BASE_DIR, "scripts", "verify_env_safety.py")]
        )
    ]

    all_passed = True
    results = []

    for name, cmd in steps:
        ok, dur, out = run_step(name, cmd)
        results.append((name, ok, dur))
        if not ok:
            all_passed = False

    print("\n" + "=" * 65)
    print(f"{'Security Audit Check':<40} {'Status':<12} {'Duration':<10}")
    print("-" * 65)
    for name, ok, dur in results:
        status_str = "PASS [OK]" if ok else "FAIL [X]"
        print(f"{name:<40} {status_str:<12} {dur:>6.2f}s")
    print("=" * 65)

    if all_passed:
        print("[+] ALL SECURITY AUDIT CHECKS PASSED: 0 Vulnerabilities Identified.")
        sys.exit(0)
    else:
        print("[!] SECURITY AUDIT FAILED: Please resolve findings above before committing.")
        sys.exit(1)


if __name__ == "__main__":
    main()
