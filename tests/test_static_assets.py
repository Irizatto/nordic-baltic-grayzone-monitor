"""Small contract checks for the no-build static frontend."""
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DashboardParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.layers = set()
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(values["id"])
        if values.get("data-layer"):
            self.layers.add(values["data-layer"])
        if tag == "script" and values.get("src"):
            self.scripts.append(values["src"])


class StaticAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.css = (ROOT / "docs" / "css" / "style.css").read_text(encoding="utf-8")
        cls.html = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
        cls.parser = DashboardParser()
        cls.parser.feed(cls.html)

    def test_css_contracts_and_accessibility_states(self):
        self.assertNotIn(r"\n.", self.css)
        self.assertRegex(self.css, r"\.events-panel\s*\{[^}]*display\s*:\s*none")
        self.assertIn(":focus-visible", self.css)
        self.assertIn("prefers-reduced-motion", self.css)
        self.assertIn("prefers-contrast", self.css)
        self.assertIn("backdrop-filter", self.css)

    def test_required_dom_hooks_are_preserved(self):
        required = {
            "map", "updated", "mode", "sourceStatus", "eventsButton",
            "layersPanel", "detailPanel", "vesselDetail", "eventsPanel",
            "eventFilter", "eventsRows", "statistics", "total", "normal",
            "watch", "high", "critical", "official", "sarTotal", "unmatched",
            "riskChart", "dataSourceStatus", "infrastructureStatus",
        }
        self.assertEqual(required - self.parser.ids, set())

    def test_layer_keys_match_the_map_groups(self):
        expected = {"vessels", "official", "sar", "cables", "pipelines", "ports", "windfarms", "areas", "helcom"}
        self.assertEqual(self.parser.layers, expected)
        map_js = (ROOT / "docs" / "js" / "map.js").read_text(encoding="utf-8")
        for layer in expected:
            self.assertRegex(map_js, rf"\b{re.escape(layer)}\s*:\s*L\.layerGroup")

    def test_script_order_and_external_library_scope(self):
        self.assertEqual(
            self.parser.scripts,
            [
                "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js",
                "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js",
                "js/layers.js", "js/map.js?v=20260715", "js/charts.js", "js/ui.js?v=20260716", "js/app.js?v=20260716", "js/events.js?v=20260715",
            ],
        )

    def test_violet_intelligence_theme_and_motion_are_present(self):
        app = (ROOT / "docs" / "js" / "app.js").read_text(encoding="utf-8")
        ui = (ROOT / "docs" / "js" / "ui.js").read_text(encoding="utf-8")
        self.assertIn("--brand: #a855f7", self.css)
        self.assertIn("aurora-drift", self.css)
        self.assertIn("--spotlight-x", self.css)
        self.assertIn("border-glow-scan", self.css)
        self.assertIn("prefers-reduced-motion: reduce", self.css)
        self.assertIn("requestAnimationFrame", app)
        self.assertIn("(pointer: fine)", ui)
        self.assertIn("css/style.css?v=20260716", self.html)

    def test_frontend_language_and_safety_notices(self):
        app = (ROOT / "docs" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("data/metadata.json", app)
        self.assertIn("escapeHtml", (ROOT / "docs" / "js" / "ui.js").read_text(encoding="utf-8"))
        self.assertIn("research lead database, not a record of confirmed incidents", self.html)
        self.assertIn("Loading public infrastructure snapshots", self.html)
        self.assertIn("review priorities, not legal or attribution determinations", self.html)
        self.assertIn("风险分数仅为审查优先级", self.html)
        self.assertNotIn("clearly labelled fictional mock vessel data", self.html)

    def test_live_data_requests_bypass_stale_browser_cache(self):
        for filename in ("app.js", "map.js", "events.js"):
            script = (ROOT / "docs" / "js" / filename).read_text(encoding="utf-8")
            self.assertIn("cache:'no-store'", script)


if __name__ == "__main__":
    unittest.main()

