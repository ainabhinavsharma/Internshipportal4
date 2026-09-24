#!/usr/bin/env python3
"""
scripts/verify_env_safety.py - Local Environment & Secret Scanner
Fulfills Phase 2 requirements of INTERNSHIPPORTAL4_LOCAL_AI_AGENT_MASTER_PLAN.md

Verifies:
1. No production database files (*.db, *.sqlite) are staged or tracked in git.
2. No active .env files are tracked in git.
3. No high-entropy production secrets (Razorpay live keys, AWS secrets, private keys) in tracked files.
4. .gitignore properly covers all critical sensitive assets.
"""
import os
import sys
import re
import subprocess

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Patterns that block release if found in tracked files
DANGEROUS_PATTERNS = [
    (r"rzp_live_[a-zA-Z0-9]{14,}", "Live Razorpay Key"),
    (r"AKIA[0-9A-Z]{16}", "AWS Access Key ID"),
    (r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----", "Private Cryptographic Key"),
    (r"AIza[0-9A-Za-z\-_]{35}", "Google API Key"),
    (r"sk-[a-zA-Z0-9]{32,}", "OpenAI Secret Key")
]

REQUIRED_GITIGNORE_ENTRIES = [
    ".env",
    "*.db*",
    "backups/",
    "uploads/"
]

def check_gitignore():
    gitignore_path = os.path.join(BASE_DIR, ".gitignore")
    if not os.path.exists(gitignore_path):
        return False, "Missing .gitignore file"
    with open(gitignore_path, "r", encoding="utf-8") as f:
        content = f.read()
    missing = [entry for entry in REQUIRED_GITIGNORE_ENTRIES if entry not in content]
    if missing:
        return False, f"Missing required .gitignore rules: {', '.join(missing)}"
    return True, "All required safety patterns present in .gitignore"

def get_tracked_files():
    try:
        res = subprocess.run(
            ["git", "ls-files"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            check=True
        )
        return res.stdout.splitlines()
    except Exception as e:
        print(f"[!] Warning: git ls-files failed: {e}")
        return []

def scan_files():
    violations = []
    tracked = get_tracked_files()
    
    print(f"[*] Scanning {len(tracked)} git-tracked files for sensitive data...")
    
    # Check for forbidden file types tracked in git
    for fpath in tracked:
        norm = fpath.lower().replace("\\", "/")
        if norm.endswith(".db") or norm.endswith(".sqlite") or norm.endswith(".sqlite3"):
            violations.append((fpath, "Database file tracked in git repository!"))
        if norm == ".env" or norm.endswith("/.env") or norm == ".env.production":
            violations.append((fpath, "Active environment credentials file tracked in git!"))

    # Scan file contents
    for fpath in tracked:
        abs_path = os.path.join(BASE_DIR, fpath)
        if not os.path.isfile(abs_path):
            continue
        # Skip binary files
        if fpath.endswith((".png", ".jpg", ".jpeg", ".ico", ".pdf", ".zip", ".woff", ".woff2")):
            continue
            
        try:
            with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                for pattern, desc in DANGEROUS_PATTERNS:
                    matches = re.findall(pattern, content)
                    if matches:
                        # Allow matching if it's explicitly in this safety checker script itself
                        if "verify_env_safety.py" in fpath:
                            continue
                        violations.append((fpath, f"Found {desc}: {matches[0][:8]}..."))
        except Exception:
            pass

    return violations

def main():
    print("=" * 60)
    print("LOCAL ENVIRONMENT & CREDENTIAL SAFETY VERIFIER")
    print("=" * 60)
    
    gi_ok, gi_msg = check_gitignore()
    print(f"[*] Checking .gitignore: {gi_msg}")
    if not gi_ok:
        print(f"[!] FAIL: {gi_msg}")
        sys.exit(1)
        
    violations = scan_files()
    if violations:
        print("\n[!] DANGEROUS DATA DETECTED IN TRACKED FILES:")
        for fpath, reason in violations:
            print(f"    - {fpath}: {reason}")
        print("\n[!] SAFETY VERIFICATION FAILED. DO NOT COMMIT.")
        sys.exit(1)
        
    print("\n[+] SUCCESS: Environment safety verified. Zero tracked secrets or databases.")
    print("=" * 60)
    sys.exit(0)

if __name__ == "__main__":
    main()
