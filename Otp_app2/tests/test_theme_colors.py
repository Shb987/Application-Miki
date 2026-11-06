import os
import re
import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_config_js_theme_colors():
    config_path = os.path.join(BASE_DIR, 'app', 'static', 'assets', 'js', 'config.js')
    with open(config_path, 'r', encoding='utf-8') as f:
        content = f.read()

    assert '#C44ECC' in content, "Primary color #C44ECC must be set in config.js"
    assert '#603CD8' in content, "Secondary color #603CD8 must be set in config.js"
    # Ensure migration away from legacy colors
    assert 'primary.toLowerCase() === "#006666"' in content


def test_color_1_css_variables_and_classes():
    color_path = os.path.join(BASE_DIR, 'app', 'static', 'assets', 'css', 'color-1.css')
    with open(color_path, 'r', encoding='utf-8') as f:
        content = f.read()

    assert '--theme-deafult: #C44ECC;' in content
    assert '--theme-secondary: #603CD8;' in content
    assert '196, 78, 204' in content
    assert '96, 60, 216' in content
    # Sidebar gradient
    assert '#C44ECC' in content and '#A33BBE' in content
    # Sidebar dark mode rules
    assert 'body.dark-only' in content


def test_style_css_theme_colors():
    style_path = os.path.join(BASE_DIR, 'app', 'static', 'assets', 'css', 'style.css')
    with open(style_path, 'r', encoding='utf-8') as f:
        content = f.read()

    assert '--theme-deafult: #C44ECC;' in content
    assert '--theme-secondary: #603CD8;' in content
    assert content.count('#006666') == 0, "No legacy #006666 should remain in style.css"
    assert content.count('0, 102, 102') == 0, "No legacy rgba(0, 102, 102) should remain in style.css"
    assert '#C44ECC' in content
    assert '#603CD8' in content


def test_base_html_theme_integration():
    base_path = os.path.join(BASE_DIR, 'app', 'templates', 'admin', 'template', 'base.html')
    with open(base_path, 'r', encoding='utf-8') as f:
        content = f.read()

    assert '#C44ECC' in content
    assert '#603CD8' in content
    assert 'localStorage.setItem("primary", "#C44ECC");' in content
    assert 'localStorage.setItem("secondary", "#603CD8");' in content
    # Check dark-only student pill color
    assert 'rgba(196, 78, 204, 0.25)' in content
    # Check logo styling
    assert 'linear-gradient(135deg, #C44ECC, #603CD8)' in content


def test_manage_roles_theme_colors():
    roles_path = os.path.join(BASE_DIR, 'app', 'templates', 'admin', 'template', 'manage_roles.html')
    with open(roles_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Verify no legacy teal/green colors remain
    for green_hex in ['#0d9488', '#0f766e', '#064e3b', '#2dd4bf', '#14b8a6', '#134e4a', 'rgba(15, 118, 110']:
        assert green_hex not in content, f"Found legacy teal/green {green_hex} in manage_roles.html"

    # Verify purple-violet gradient in banner card and buttons
    assert 'linear-gradient(90deg, #9d2cb0 0%, #7e22ce 45%, #501680 100%)' in content
    assert 'linear-gradient(135deg, #C44ECC, #603CD8)' in content
    assert '#603CD8' in content
    assert '#C44ECC' in content

    # Verify dark mode uses glowing violet/purple
    assert '#c084fc' in content
    assert '#e879f9' in content


def test_staff_tasks_monitoring_theme_colors():
    staff_path = os.path.join(BASE_DIR, 'app', 'templates', 'admin', 'template', 'staff_tasks_monitoring.html')
    with open(staff_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Verify primary theme variables are purple-violet
    assert '--primary-teal: #603CD8;' in content
    assert '--primary-teal-light: #C44ECC;' in content
    assert '#0f766e' not in content


