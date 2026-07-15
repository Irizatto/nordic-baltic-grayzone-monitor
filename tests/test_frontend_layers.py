"""Static integration checks for the left-side Leaflet layer controls."""
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FrontendLayerToggleTests(unittest.TestCase):
    def test_every_infrastructure_layer_has_an_independent_toggle(self):
        html = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
        map_js = (ROOT / "docs" / "js" / "map.js").read_text(encoding="utf-8")
        for layer_name in ("cables", "pipelines", "ports", "windfarms", "areas"):
            self.assertIn(f'data-layer="{layer_name}"', html)
            self.assertIn(f"{layer_name}:L.layerGroup().addTo(map)", map_js)
        self.assertIn("file:'sensitive_areas.geojson'", map_js)

    def test_switch_handler_adds_and_removes_the_selected_group(self):
        ui_js = (ROOT / "docs" / "js" / "ui.js").read_text(encoding="utf-8")
        self.assertIn("window.groups?.[input.dataset.layer]", ui_js)
        self.assertIn("group.addTo(map)", ui_js)
        self.assertIn("map.removeLayer(group)", ui_js)


if __name__ == "__main__":
    unittest.main()
