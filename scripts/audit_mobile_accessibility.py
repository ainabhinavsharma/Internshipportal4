"""
scripts/audit_mobile_accessibility.py
Audits HTML templates and CSS for Phase 18 (Mobile & Accessibility Responsive Audit)
of INTERNSHIPPORTAL4_LOCAL_AI_AGENT_MASTER_PLAN.md.
"""

import os
import sys
import re
from html.parser import HTMLParser

# Ensure standard output can print UTF-8 safely on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

VIEWPORTS = [
    (360, 800, "Mobile Small (Galaxy S20 / Android)"),
    (390, 844, "Mobile Standard (iPhone 12/13/14)"),
    (412, 915, "Mobile Large (Pixel 7)"),
    (768, 1024, "Tablet (iPad)"),
    (1366, 768, "Laptop (Standard 1366x768)"),
    (1920, 1080, "Desktop (FHD 1920x1080)")
]

CRITICAL_WORKFLOWS = {
    "signup": ["index.html", "company_signup.html"],
    "login": ["index.html", "company_login.html", "admin_login.html", "reset_password.html"],
    "portal": ["portal.html", "portal_ledger.html"],
    "courses": ["courses_catalog.html", "course_detail.html", "course_learn.html", "course_pay.html", "course_quiz.html", "course_submit_project.html"],
    "tasks": ["tasks_list.html", "staff_task_queue.html"],
    "applications": ["post_listings.html", "post_detail.html", "company_applicants.html", "admin_job_applications.html"],
    "payment": ["course_pay.html", "portal.html", "admin_course_payments.html", "admin_post_hire_deposits.html"],
    "admin": ["admin.html", "admin_login.html", "admin_ledger.html", "admin_companies.html"],
    "company": ["company_dashboard.html", "company_profile.html", "company_profile_edit.html", "post_form.html"]
}


class TemplateAccessibilityParser(HTMLParser):
    def __init__(self, filename):
        super().__init__()
        self.filename = filename
        self.inputs = []
        self.labels = {}
        self.modals = []
        self.has_viewport = False
        self.has_skip_link = False
        self.has_main_landmark = False
        self.alerts = []
        
    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        
        if tag == "meta" and attr_dict.get("name") == "viewport":
            self.has_viewport = True
            
        if tag == "a" and "skip-link" in attr_dict.get("class", ""):
            self.has_skip_link = True
            
        if tag == "main" or attr_dict.get("role") == "main" or attr_dict.get("id") == "main-content":
            self.has_main_landmark = True
            
        if tag in ["input", "select", "textarea"]:
            inp_type = attr_dict.get("type", "text").lower()
            if inp_type not in ["hidden", "submit", "button", "reset"]:
                self.inputs.append({
                    "tag": tag,
                    "type": inp_type,
                    "id": attr_dict.get("id"),
                    "name": attr_dict.get("name"),
                    "aria_label": attr_dict.get("aria-label"),
                    "aria_labelledby": attr_dict.get("aria-labelledby"),
                    "placeholder": attr_dict.get("placeholder", "")[:30]
                })
                
        elif tag == "label":
            for_id = attr_dict.get("for")
            if for_id:
                self.labels[for_id] = True
                
        cls = attr_dict.get("class", "").lower()
        elem_id = attr_dict.get("id", "").lower()
        role = attr_dict.get("role", "")
        
        # Modal detection
        if role == "dialog" or "modal" in cls or "modal" in elem_id:
            # Exclude false positives like modal-btn, modal-header, etc.
            if any(term in cls.split() or term == elem_id for term in ["modal", "modal-overlay", "wizard-overlay"]):
                self.modals.append({
                    "id": attr_dict.get("id", ""),
                    "class": attr_dict.get("class", ""),
                    "role": role,
                    "aria_modal": attr_dict.get("aria-modal"),
                    "aria_labelledby": attr_dict.get("aria-labelledby"),
                    "aria_label": attr_dict.get("aria-label")
                })
                
        if role == "alert" or "alert" in cls or "error" in cls:
            self.alerts.append({
                "id": attr_dict.get("id", ""),
                "class": attr_dict.get("class", ""),
                "role": role,
                "aria_live": attr_dict.get("aria-live")
            })


def audit_templates():
    results = {}
    templates_dir = "templates"
    
    for root, dirs, files in os.walk(templates_dir):
        for f in sorted(files):
            if not f.endswith(".html"):
                continue
            path = os.path.join(root, f)
            with open(path, "r", encoding="utf-8", errors="ignore") as fp:
                content = fp.read()
                
            parser = TemplateAccessibilityParser(f)
            # If template includes _head.html, viewport is provided
            if "_head.html" in content:
                parser.has_viewport = True
                
            try:
                parser.feed(content)
            except Exception:
                pass
                
            unlabeled = []
            for inp in parser.inputs:
                inp_id = inp["id"]
                has_label = (inp_id and inp_id in parser.labels) or inp["aria_label"] or inp["aria_labelledby"]
                if not has_label:
                    unlabeled.append(inp)
                    
            results[f] = {
                "has_viewport": parser.has_viewport,
                "total_inputs": len(parser.inputs),
                "unlabeled_inputs": unlabeled,
                "modals": parser.modals,
                "has_skip_link": parser.has_skip_link,
                "has_main_landmark": parser.has_main_landmark
            }
            
    return results


def audit_css_media_queries():
    css_path = os.path.join("static", "css", "dbert-theme.css")
    with open(css_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
        
    queries = re.findall(r"@media\s*\([^\)]+\)", content)
    has_focus_visible = ":focus-visible" in content
    has_reduced_motion = "prefers-reduced-motion" in content
    has_mobile_font_guard = "16px" in content and "@media" in content
    
    return {
        "media_queries_count": len(queries),
        "queries": queries[:10],
        "has_focus_visible": has_focus_visible,
        "has_reduced_motion": has_reduced_motion,
        "has_mobile_font_guard": has_mobile_font_guard
    }


if __name__ == "__main__":
    print("=" * 60)
    print("PHASE 18 — MOBILE & ACCESSIBILITY AUDIT ENGINE")
    print("=" * 60)
    
    css_res = audit_css_media_queries()
    print(f"\n[*] CSS Media Queries Found: {css_res['media_queries_count']}")
    print(f"[*] Focus-visible styling present: {css_res['has_focus_visible']}")
    print(f"[*] Prefers-reduced-motion support: {css_res['has_reduced_motion']}")
    print(f"[*] iOS auto-zoom 16px font guard: {css_res['has_mobile_font_guard']}")
    
    template_res = audit_templates()
    print(f"\n[*] Audited {len(template_res)} templates:")
    
    missing_viewport = [k for k, v in template_res.items() if not v["has_viewport"] and not k.startswith("_")]
    print(f"[*] Templates missing viewport: {len(missing_viewport)}")
    if missing_viewport:
        print(f"    Missing: {missing_viewport}")
        
    modals_without_dialog = []
    for t_name, data in template_res.items():
        for m in data["modals"]:
            if m["role"] != "dialog" or not m["aria_modal"]:
                modals_without_dialog.append((t_name, m))
                
    print(f"\n[*] Modals without role='dialog' and aria-modal='true': {len(modals_without_dialog)}")
    for t, m in modals_without_dialog:
        print(f"    - {t}: id='{m['id']}' class='{m['class']}'")
        
    print("\n[*] Critical Workflows Status:")
    for wf, tmpls in CRITICAL_WORKFLOWS.items():
        wf_unlabeled = sum(len(template_res.get(t, {}).get("unlabeled_inputs", [])) for t in tmpls)
        print(f"    - Workflow '{wf}' ({len(tmpls)} templates): {wf_unlabeled} unlabeled inputs")
        if wf_unlabeled > 0:
            for t in tmpls:
                unl = template_res.get(t, {}).get("unlabeled_inputs", [])
                if unl:
                    print(f"      * {t}: {len(unl)} unlabeled -> {[x.get('id') or x.get('placeholder') for x in unl[:4]]}")
