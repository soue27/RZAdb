from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient

from app.presentation.app import app


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_ROOT = PROJECT_ROOT / "app/presentation/templates"
STATIC_ROOT = PROJECT_ROOT / "app/presentation/static"

LOCAL_ASSETS = {
    "/static/vendor/bootstrap/bootstrap.min.css": "text/css",
    "/static/vendor/bootstrap/bootstrap.bundle.min.js": "text/javascript",
    "/static/vendor/bootstrap/bootstrap.min.css.map.json": "application/json",
    "/static/vendor/bootstrap/bootstrap.bundle.min.js.map.json": "application/json",
    "/static/vendor/htmx/htmx.min.js": "text/javascript",
    "/static/css/fonts.css": "text/css",
    "/static/css/app.css": "text/css",
    "/static/js/theme.js": "text/javascript",
    "/static/js/sidebar.js": "text/javascript",
    "/static/js/tabs.js": "text/javascript",
    "/static/js/htmx.js": "text/javascript",
    "/static/fonts/roboto/roboto-300.ttf": "font/ttf",
    "/static/fonts/roboto/roboto-400.ttf": "font/ttf",
    "/static/fonts/roboto/roboto-500.ttf": "font/ttf",
    "/static/fonts/roboto/roboto-700.ttf": "font/ttf",
    "/static/fonts/material-icons/material-icons.ttf": "font/ttf",
}


class _ResourceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.resources: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag in {"script", "img", "source", "iframe", "audio", "video"}:
            source = attributes.get("src")
            if source:
                self.resources.append(source)
        elif tag == "link" and "stylesheet" in attributes.get("rel", "").split():
            href = attributes.get("href")
            if href:
                self.resources.append(href)


@pytest.mark.parametrize(("path", "content_type"), LOCAL_ASSETS.items())
def test_local_ui_assets_are_served_with_expected_mime_types(
    path: str,
    content_type: str,
) -> None:
    response = TestClient(app).get(path)

    assert response.status_code == 200
    assert response.headers["content-type"].split(";", maxsplit=1)[0] == content_type
    assert response.content


def test_templates_reference_only_local_static_resources() -> None:
    external_resources: list[tuple[Path, str]] = []
    for template_path in TEMPLATES_ROOT.rglob("*.html"):
        template = template_path.read_text(encoding="utf-8")
        parser = _ResourceParser()
        parser.feed(template)
        for resource in parser.resources:
            parsed = urlparse(resource)
            if parsed.scheme or parsed.netloc or not parsed.path.startswith("/static/"):
                external_resources.append((template_path, resource))
        assert re.search(r"@import\s", template, re.IGNORECASE) is None
        assert re.search(
            r"url\(\s*['\"]?(?:https?:)?//", template, re.IGNORECASE
        ) is None

    assert external_resources == []


def test_css_has_no_external_imports_or_external_urls() -> None:
    css_files = list(STATIC_ROOT.rglob("*.css"))

    assert css_files
    for css_path in css_files:
        css = css_path.read_text(encoding="utf-8")
        assert re.search(r"@import\s", css, re.IGNORECASE) is None
        assert re.search(r"url\(\s*['\"]?(?:https?:)?//", css, re.IGNORECASE) is None


def test_local_vendor_files_preserve_pinned_library_versions_and_font_weights() -> None:
    bootstrap_css = (STATIC_ROOT / "vendor/bootstrap/bootstrap.min.css").read_text(
        encoding="utf-8"
    )
    bootstrap_js = (
        STATIC_ROOT / "vendor/bootstrap/bootstrap.bundle.min.js"
    ).read_text(encoding="utf-8")
    vendor_notes = (STATIC_ROOT / "vendor/README.md").read_text(encoding="utf-8")
    fonts_css = (STATIC_ROOT / "css/fonts.css").read_text(encoding="utf-8")

    assert "Bootstrap  v5.3.8" in bootstrap_css
    assert "Bootstrap v5.3.8" in bootstrap_js
    assert "Bootstrap CSS и Bundle | 5.3.8" in vendor_notes
    assert "HTMX | 2.0.7" in vendor_notes
    for weight in (300, 400, 500, 700):
        assert f"font-weight: {weight};" in fonts_css
    assert "font-family: \"Material Icons\";" in fonts_css
