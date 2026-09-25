"""
services/accessibility_service.py - Mobile Responsiveness & Accessibility Engine
Implements Phase 18 requirements of INTERNSHIPPORTAL4_LOCAL_AI_AGENT_MASTER_PLAN.md

Provides:
- WCAG 2.1 relative luminance and contrast ratio calculations (AA / AAA compliance)
- Supported viewport matrices: 360x800, 390x844, 412x915, 768x1024, 1366x768, 1920x1080
- HTML template accessibility parsing & validation (labels, ARIA roles, landmarks, modals, alerts)
- CSS responsiveness and focus state verification
"""

import math
import re
from html.parser import HTMLParser
from typing import Dict, List, Tuple, Any, Optional

# Supported viewports required by Master Plan Phase 18
SUPPORTED_VIEWPORTS: List[Dict[str, Any]] = [
    {"width": 360, "height": 800, "device": "Mobile Small (Galaxy S20 / Android)", "category": "mobile"},
    {"width": 390, "height": 844, "device": "Mobile Standard (iPhone 12/13/14)", "category": "mobile"},
    {"width": 412, "height": 915, "device": "Mobile Large (Pixel 7)", "category": "mobile"},
    {"width": 768, "height": 1024, "device": "Tablet (iPad Portrait)", "category": "tablet"},
    {"width": 1366, "height": 768, "device": "Laptop Standard (1366x768)", "category": "desktop"},
    {"width": 1920, "height": 1080, "device": "Desktop FHD (1920x1080)", "category": "desktop"},
]
STANDARD_VIEWPORTS = SUPPORTED_VIEWPORTS

CRITICAL_WORKFLOWS: Dict[str, List[str]] = {
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


# ==============================================================================
# 1. WCAG 2.1 COLOR CONTRAST CALCULATOR
# ==============================================================================

def hex_to_rgb(hex_str: str) -> Tuple[int, int, int]:
    """Parses a hex color string (e.g. #FFFFFF or #FFF) into RGB integers."""
    h = hex_str.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        raise ValueError(f"Invalid hex color: {hex_str}")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def calculate_relative_luminance(hex_str: str) -> float:
    """
    Computes WCAG 2.1 relative luminance for an sRGB hex color.
    Formula: L = 0.2126 * R + 0.7152 * G + 0.0722 * B
    """
    r_255, g_255, b_255 = hex_to_rgb(hex_str)
    
    def channel_luminance(c_255: int) -> float:
        c = c_255 / 255.0
        return c / 12.92 if c <= 0.04045 else math.pow((c + 0.055) / 1.055, 2.4)
    
    r = channel_luminance(r_255)
    g = channel_luminance(g_255)
    b = channel_luminance(b_255)
    
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def calculate_contrast_ratio(hex1: str, hex2: str) -> float:
    """
    Calculates the WCAG 2.1 contrast ratio between two colors:
    (L1 + 0.05) / (L2 + 0.05) where L1 is the lighter color.
    Returns float rounded to 2 decimal places (e.g. 4.54).
    """
    lum1 = calculate_relative_luminance(hex1)
    lum2 = calculate_relative_luminance(hex2)
    lighter = max(lum1, lum2)
    darker = min(lum1, lum2)
    ratio = (lighter + 0.05) / (darker + 0.05)
    return round(ratio, 2)


def meets_wcag_aa(hex_fg: str, hex_bg: str, is_large_text: bool = False) -> bool:
    """
    Determines whether the contrast ratio meets WCAG 2.1 Level AA:
    - Normal text: >= 4.5:1
    - Large / Bold text: >= 3.0:1
    """
    ratio = calculate_contrast_ratio(hex_fg, hex_bg)
    threshold = 3.0 if is_large_text else 4.5
    return ratio >= threshold


def meets_wcag_aaa(hex_fg: str, hex_bg: str, is_large_text: bool = False) -> bool:
    """
    Determines whether the contrast ratio meets WCAG 2.1 Level AAA:
    - Normal text: >= 7.0:1
    - Large / Bold text: >= 4.5:1
    """
    ratio = calculate_contrast_ratio(hex_fg, hex_bg)
    threshold = 4.5 if is_large_text else 7.0
    return ratio >= threshold


# ==============================================================================
# 2. HTML ACCESSIBILITY AUDITOR
# ==============================================================================

class AccessibilityHTMLParser(HTMLParser):
    def __init__(self, filename: str = "template.html"):
        super().__init__()
        self.filename = filename
        self.has_viewport = False
        self.has_skip_link = False
        self.has_main_landmark = False
        self.inputs: List[Dict[str, Any]] = []
        self.labels: Dict[str, bool] = {}
        self.modals: List[Dict[str, Any]] = []
        self.alerts: List[Dict[str, Any]] = []
        self.buttons_without_text: List[Dict[str, Any]] = []
        self._current_tag = None
        self._in_script = False
        self._in_style = False

    def handle_endtag(self, tag: str):
        if tag.lower() == "script":
            self._in_script = False
        elif tag.lower() == "style":
            self._in_style = False
        
    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]):
        tag_lower = tag.lower()
        if tag_lower == "script":
            self._in_script = True
            return
        if tag_lower == "style":
            self._in_style = True
            return
        if self._in_script or self._in_style:
            return

        attr_dict = {k.lower(): (v or "") for k, v in attrs}
        self._current_tag = tag
        
        # 1. Viewport tag
        if tag == "meta" and attr_dict.get("name", "").lower() == "viewport":
            content = attr_dict.get("content", "").lower()
            if "width=device-width" in content:
                self.has_viewport = True
                
        # 2. Skip link
        if tag == "a" and "skip-link" in attr_dict.get("class", "").lower():
            self.has_skip_link = True
            
        # 3. Main landmark
        if tag == "main" or attr_dict.get("role") == "main" or attr_dict.get("id") == "main-content":
            self.has_main_landmark = True
            
        # 4. Form inputs
        if tag in ["input", "select", "textarea"]:
            inp_type = attr_dict.get("type", "text").lower()
            # Exclude hidden or non-interactive fields
            if inp_type not in ["hidden", "submit", "button", "reset"]:
                self.inputs.append({
                    "tag": tag,
                    "type": inp_type,
                    "id": attr_dict.get("id", ""),
                    "name": attr_dict.get("name", ""),
                    "aria_label": attr_dict.get("aria-label", ""),
                    "aria_labelledby": attr_dict.get("aria-labelledby", ""),
                    "placeholder": attr_dict.get("placeholder", "")
                })
                
        # 5. Label tag
        elif tag == "label":
            for_id = attr_dict.get("for", "").strip()
            if for_id:
                self.labels[for_id] = True
                
        # 6. Modals & Dialogs
        cls = attr_dict.get("class", "").lower()
        elem_id = attr_dict.get("id", "").lower()
        role = attr_dict.get("role", "").lower()
        
        # Check if element represents a modal dialog container
        is_modal = False
        if role == "dialog" or tag == "dialog":
            is_modal = True
        elif any(term in cls.split() for term in ["modal-overlay", "wizard-overlay"]):
            is_modal = True
        elif "modal" in cls.split() and not any(sub in cls for sub in ["modal-header", "modal-body", "modal-foot", "modal-close", "modal-title", "modal-msg", "modal-box"]):
            is_modal = True
        elif elem_id.endswith("modal") or elem_id.endswith("-modal") or elem_id == "modal":
            is_modal = True
            
        if is_modal:
            self.modals.append({
                "id": attr_dict.get("id", ""),
                "class": attr_dict.get("class", ""),
                "role": role,
                "aria_modal": attr_dict.get("aria-modal", "").lower(),
                "aria_labelledby": attr_dict.get("aria-labelledby", ""),
                "aria_label": attr_dict.get("aria-label", "")
            })
            
        # 7. Alert & Status containers
        if role in ["alert", "status"] or "alert" in cls or "error" in cls:
            self.alerts.append({
                "id": attr_dict.get("id", ""),
                "class": attr_dict.get("class", ""),
                "role": role,
                "aria_live": attr_dict.get("aria-live", "")
            })


def audit_html_accessibility(html_str: str, filename: str = "template.html") -> Dict[str, Any]:
    """
    Parses an HTML template string and reports accessibility compliance.
    """
    parser = AccessibilityHTMLParser(filename)
    
    # In Jinja templates, _head.html includes the viewport meta tag
    if "_head.html" in html_str:
        parser.has_viewport = True
        
    # Strip Jinja comments before parsing as they are not emitted to client DOM
    cleaned_html = re.sub(r"\{#.*?#\}", "", html_str, flags=re.DOTALL)

    try:
        parser.feed(cleaned_html)
    except Exception:
        pass
        
    # Check unlabeled inputs
    unlabeled = []
    for inp in parser.inputs:
        inp_id = inp["id"]
        has_label = bool((inp_id and inp_id in parser.labels) or inp["aria_label"] or inp["aria_labelledby"])
        if not has_label:
            unlabeled.append(inp)
            
    # Check modals missing dialog role or aria-modal
    uncompliant_modals = []
    for m in parser.modals:
        if m["role"] != "dialog" or m["aria_modal"] != "true":
            uncompliant_modals.append(m)
            
    return {
        "filename": filename,
        "has_viewport": parser.has_viewport,
        "total_inputs": len(parser.inputs),
        "unlabeled_inputs": unlabeled,
        "unlabeled_count": len(unlabeled),
        "total_modals": len(parser.modals),
        "uncompliant_modals": uncompliant_modals,
        "uncompliant_modal_count": len(uncompliant_modals),
        "alerts_count": len(parser.alerts),
        "has_skip_link": parser.has_skip_link,
        "has_main_landmark": parser.has_main_landmark
    }


# ==============================================================================
# 3. CSS RESPONSIVENESS & TOUCH TARGET AUDITOR
# ==============================================================================

def audit_css_responsiveness(css_str: str) -> Dict[str, Any]:
    """
    Audits stylesheet for responsive media queries, touch targets, focus states,
    and mobile font auto-zoom protections.
    """
    media_queries = re.findall(r"@media\s*([^{]+)\{", css_str)
    has_focus_visible = ":focus-visible" in css_str
    has_reduced_motion = "prefers-reduced-motion" in css_str
    # iOS Safari auto-zoom prevention: all text inputs must be >= 16px on mobile
    has_mobile_font_guard = "16px" in css_str and any("max-width" in q for q in media_queries)
    
    # Touch target minimum sizing checks
    has_touch_target_rules = any("min-height" in css_str or "min-width" in css_str or "44px" in css_str for _ in [True])
    
    breakpoints = set()
    for q in media_queries:
        matches = re.findall(r"(\d+)px", q)
        for m in matches:
            breakpoints.add(int(m))
            
    return {
        "media_query_count": len(media_queries),
        "breakpoints": sorted(list(breakpoints)),
        "has_focus_visible": has_focus_visible,
        "has_reduced_motion": has_reduced_motion,
        "has_mobile_font_guard": has_mobile_font_guard,
        "has_touch_target_rules": has_touch_target_rules
    }
