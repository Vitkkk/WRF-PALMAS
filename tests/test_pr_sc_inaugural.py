"""Fast static smoke tests for commemorative PR/SC WRF configuration and diagnostics."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from plot_severe_pr_sc import earth_relative, interpolate_agl


class InauguralSmokeTest(unittest.TestCase):
    def test_pr_sc_namelist_and_reflectivity(self):
        with tempfile.TemporaryDirectory() as t:
            out = Path(t)
            result = subprocess.run([
                sys.executable, str(ROOT / "scripts" / "make_namelists.py"),
                "--start", "2026-11-07T12:00", "--hours", "6",
                "--grid", "151", "--grid-y", "141", "--dx-km", "6",
                "--vert-levels", "42", "--history-minutes", "30",
                "--lat", "-26.0", "--lon", "-51.5", "--cumulus", "0",
                "--radar", "--geog", "/tmp/prsc-test-geog", "--out", str(out),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            wps = (out / "namelist.wps").read_text()
            wrf = (out / "namelist.input").read_text()
            self.assertIn("e_we = 151,", wps)
            self.assertIn("e_sn = 141,", wps)
            self.assertIn("end_date = '2026-11-07_18:00:00'", wps)
            self.assertIn("run_hours = 6,", wrf)
            self.assertIn("e_vert = 42,", wrf)
            self.assertIn("history_interval = 30,", wrf)
            self.assertIn("do_radar_ref = 1,", wrf)
            self.assertIn("cu_physics = 0,", wrf)

    def test_earth_wind_rotation(self):
        import numpy as np
        u, v = earth_relative(np.array([10.]), np.array([0.]),
                              np.array([0.]), np.array([1.]))
        np.testing.assert_allclose(u, [0.])
        np.testing.assert_allclose(v, [10.])

    def test_vertical_interpolation(self):
        import numpy as np
        z = np.array([100., 1100., 6100.])[:, None, None]
        u = np.array([2., 12., 22.])[:, None, None]
        self.assertAlmostEqual(interpolate_agl(z, u, 1000.)[0, 0], 11.0)
        self.assertAlmostEqual(interpolate_agl(z, u, 6000.)[0, 0], 21.8)


if __name__ == "__main__":
    unittest.main()
