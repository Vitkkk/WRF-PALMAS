"""Small physical/display checks for V0.4 radar palette and border diagnostics."""
import importlib.util
from pathlib import Path
import unittest

import numpy as np

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "plot_v04.py"
SPEC = importlib.util.spec_from_file_location("plot_v04", SCRIPT)
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


class RadarPanelTests(unittest.TestCase):
    def test_palette_bounds_and_colors(self):
        cmap, norm = M.radar_palette()
        self.assertEqual(len(M.RADAR_BOUNDS), 13)
        self.assertEqual(cmap.N, 12)
        self.assertEqual(norm.boundaries[-1], 90)
        self.assertEqual(norm.boundaries[0], -30)
        bins = norm(np.array([5, 15, 25, 35, 45, 55, 65, 75, 85]))
        self.assertTrue(np.all(np.diff(bins) > 0))

    def test_no_echo_mask(self):
        data = np.array([[np.nan, -10., -0.1, 0., 20., 50.]])
        visible = M.rain_display_field(data)
        self.assertEqual(visible.mask.tolist(), [[True, True, True, False, False, False]])

    def test_edge_echo(self):
        rain = np.full((12, 16), np.nan)
        rain[5, 7] = 60.
        self.assertFalse(M.edge_echo(rain))
        rain[0, 9] = 35.
        self.assertTrue(M.edge_echo(rain))

    def test_internal_diagnostics_metadata(self):
        # Border products should never quietly accept 3-D input.
        with self.assertRaises(ValueError):
            M.edge_echo(np.ones((2, 3, 4)))


if __name__ == "__main__":
    unittest.main()
