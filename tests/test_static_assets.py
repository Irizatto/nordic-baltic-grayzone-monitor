"""Small contract checks for the no-build static frontend."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class StaticAssetTests(unittest.TestCase):
    def test_css_has_no_literal_backslash_newline_tokens(self):
        css = (ROOT / "docs" / "css" / "style.css").read_text(encoding="utf-8")
        self.assertNotIn(r"\n.", css)
        self.assertIn(".events-panel{display:none", css)

    def test_frontend_reads_failure_metadata_and_normal_level(self):
        app = (ROOT / "docs" / "js" / "app.js").read_text(encoding="utf-8")
        html = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
        self.assertIn("data/metadata.json", app)
        self.assertIn("escapeHtml", (ROOT / "docs" / "js" / "ui.js").read_text(encoding="utf-8"))
        self.assertIn('id="normal"', html)
        self.assertNotIn("clearly labelled fictional mock vessel data", html)


if __name__ == "__main__":
    unittest.main()
