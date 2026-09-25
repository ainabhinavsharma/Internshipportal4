"""
tests/test_mobile_accessibility.py
Phase 18 (MOB-001 - MOB-003): Automated Mobile & Accessibility Test Suite.

Verifies:
1. Viewport matrix across all 6 target form-factors (360x800, 390x844, 412x915, 768x1024, 1366x768, 1920x1080).
2. CSS responsiveness: media query breakpoints, mobile 44px touch targets, iOS Safari 16px auto-zoom guard.
3. WCAG 2.1 AA color contrast formulas, gold focus-visible rings, skip-to-content links, main landmarks.
4. Modal dialog accessibility: role="dialog", aria-modal="true", aria-labelledby, and ESC keyboard handler.
5. Form labels and accessible names across all 9 critical user journeys.
"""

from pathlib import Path
import pytest
from services.accessibility_service import (
    STANDARD_VIEWPORTS,
    CRITICAL_WORKFLOWS,
    calculate_relative_luminance,
    calculate_contrast_ratio,
    meets_wcag_aa,
    meets_wcag_aaa,
    audit_html_accessibility,
    audit_css_responsiveness,
)

TEMPLATES_DIR = Path("templates")
CSS_FILE = Path("static/css/dbert-theme.css")
JS_CREATIVE_UI = Path("static/js/creative-ui.js")


class TestViewportMatrix:
    """Verifies all 6 required viewports, viewport tags, touch targets, and iOS zoom guards."""

    def test_standard_viewports_defined(self):
        """All 6 standard viewports specified in Phase 18 must be defined."""
        widths = {vp["width"]: vp["height"] for vp in STANDARD_VIEWPORTS}
        assert len(STANDARD_VIEWPORTS) == 6
        assert 360 in widths and widths[360] == 800   # Galaxy S20
        assert 390 in widths and widths[390] == 844   # iPhone 12/13/14
        assert 412 in widths and widths[412] == 915   # Pixel 7
        assert 768 in widths and widths[768] == 1024  # iPad
        assert 1366 in widths and widths[1366] == 768 # Laptop
        assert 1920 in widths and widths[1920] == 1080 # FHD Desktop

    def test_css_responsiveness_and_touch_targets(self):
        """CSS stylesheet must define media queries, touch targets >= 44px, and iOS 16px guards."""
        assert CSS_FILE.exists(), "dbert-theme.css must exist"
        css_text = CSS_FILE.read_text(encoding="utf-8")
        audit = audit_css_responsiveness(css_text)

        assert audit["media_query_count"] >= 10, f"Expected >= 10 media queries, got {audit['media_query_count']}"
        assert audit["has_focus_visible"], "CSS must contain :focus-visible rules"
        assert audit["has_reduced_motion"], "CSS must support prefers-reduced-motion"
        assert audit["has_touch_target_rules"], "CSS must contain touch target rules (min-height/width 44px)"
        assert audit["has_mobile_font_guard"], "CSS must enforce >= 16px font on inputs to prevent iOS auto-zoom"

        # Check mobile touch targets explicitly
        assert "min-height: 44px" in css_text or "min-height:44px" in css_text
        assert "min-width: 44px" in css_text or "min-width:44px" in css_text

    def test_html_templates_contain_viewport_meta(self):
        """All critical workflow HTML templates must specify width=device-width viewport."""
        for workflow, templates in CRITICAL_WORKFLOWS.items():
            for tpl in templates:
                tpl_path = TEMPLATES_DIR / tpl
                assert tpl_path.exists(), f"Template {tpl} must exist"
                content = tpl_path.read_text(encoding="utf-8")
                audit = audit_html_accessibility(content, tpl)
                assert audit["has_viewport"], f"Template {tpl} in workflow '{workflow}' must include viewport meta tag"


class TestColorContrastAndFocus:
    """Verifies WCAG 2.1 AA luminance and contrast calculations and keyboard focus states."""

    def test_luminance_and_contrast_ratio_formula(self):
        """Pure black (#000000) and pure white (#ffffff) must have a 21:1 contrast ratio."""
        lum_white = calculate_relative_luminance("#ffffff")
        lum_black = calculate_relative_luminance("#000000")
        assert round(lum_white, 4) == 1.0
        assert round(lum_black, 4) == 0.0

        ratio = calculate_contrast_ratio("#ffffff", "#000000")
        assert ratio == 21.0
        assert meets_wcag_aa("#ffffff", "#000000")
        assert meets_wcag_aaa("#ffffff", "#000000")

    def test_dbert_brand_colors_contrast(self):
        """Key UI elements (e.g. green status badge, dark backgrounds) must meet WCAG AA >= 4.5:1."""
        # White text on green badge (#15803d)
        badge_ratio = calculate_contrast_ratio("#ffffff", "#15803d")
        assert badge_ratio >= 4.5, f"Green badge contrast {badge_ratio} must meet WCAG AA (>= 4.5:1)"
        assert meets_wcag_aa("#ffffff", "#15803d")

        # White text on dark navy card background (#0d1322)
        card_ratio = calculate_contrast_ratio("#ffffff", "#0d1322")
        assert card_ratio >= 15.0
        assert meets_wcag_aa("#ffffff", "#0d1322")

    def test_focus_visible_ring_in_css(self):
        """Focus-visible must use high contrast outline and offset."""
        css_text = CSS_FILE.read_text(encoding="utf-8")
        assert ":focus-visible" in css_text
        assert "outline:" in css_text
        assert "outline-offset:" in css_text

    def test_skip_link_and_landmarks(self):
        """App shell and landing page must contain skip-link and main content landmark."""
        app_shell = (TEMPLATES_DIR / "_app_shell.html").read_text(encoding="utf-8")
        assert "skip-link" in app_shell
        assert 'href="#main-content"' in app_shell

        index_html = (TEMPLATES_DIR / "index.html").read_text(encoding="utf-8")
        assert "skip-link" in index_html
        assert 'id="main-content"' in index_html


class TestModalAccessibilityAndEscape:
    """Verifies modal containers have ARIA roles and global ESC key handler."""

    def test_modal_aria_attributes(self):
        """All critical modals across the application must have role='dialog' and aria-modal='true'."""
        modal_templates = [
            "admin.html",
            "mentor.html",
            "tasks_list.html",
            "staff_task_queue.html",
            "post_detail.html",
            "course_learn.html",
            "course_quiz.html",
            "portal.html",
        ]
        for tpl in modal_templates:
            content = (TEMPLATES_DIR / tpl).read_text(encoding="utf-8")
            audit = audit_html_accessibility(content, tpl)
            assert audit["uncompliant_modal_count"] == 0, (
                f"Template {tpl} has uncompliant modals: {audit['uncompliant_modals']}"
            )

    def test_universal_modal_accessibility_js(self):
        """creative-ui.js must register Escape key handler and backdrop dismissal."""
        assert JS_CREATIVE_UI.exists()
        js_text = JS_CREATIVE_UI.read_text(encoding="utf-8")
        assert "initUniversalModalAccessibility" in js_text
        assert "Escape" in js_text


class TestCriticalWorkflowsFormLabels:
    """Verifies form controls in all 9 critical workflows have accessible labels."""

    @pytest.mark.parametrize("workflow", list(CRITICAL_WORKFLOWS.keys()))
    def test_workflow_form_labels(self, workflow: str):
        """Every input/select/textarea in workflow templates must have an accessible label."""
        templates = CRITICAL_WORKFLOWS[workflow]
        for tpl in templates:
            tpl_path = TEMPLATES_DIR / tpl
            content = tpl_path.read_text(encoding="utf-8")
            audit = audit_html_accessibility(content, tpl)
            assert audit["unlabeled_count"] == 0, (
                f"Workflow '{workflow}' - Template {tpl} has {audit['unlabeled_count']} unlabeled inputs: "
                f"{audit['unlabeled_inputs']}"
            )
