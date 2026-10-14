"""Analytic checks of V0.3 physical diagnostics; no WRF needed."""
import importlib.util
from pathlib import Path
import unittest

import numpy as np

FILE = Path(__file__).resolve().parents[1] / "scripts" / "diagnostics_v03.py"
SPEC = importlib.util.spec_from_file_location("diagnostics_v03", FILE)
D = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(D)


class V03DiagnosticsTest(unittest.TestCase):
    def test_solid_body_rotation(self):
        """u=-omega*y, v=omega*x => zeta=2*omega."""
        omega = 0.001
        nz, ny, nx = 2, 12, 16
        dx, dy = 500.0, 400.0
        y = np.arange(ny)[None, :, None] * dy
        x = np.arange(nx)[None, None, :] * dx
        u = np.broadcast_to(-omega * y, (nz, ny, nx + 1))
        v = np.broadcast_to(omega * x, (nz, ny + 1, nx))
        zeta = D.vertical_vorticity(u, v, dx, dy)
        self.assertEqual(zeta.shape, (nz, ny, nx))
        self.assertTrue(np.allclose(zeta, 0.002))

    def test_rain_reflectivity_increases_with_liquid_water(self):
        qr = np.array([0.0, 1e-6, 1e-4, 1e-3])[None, :, None]
        p = np.full_like(qr, 90000.)
        result = D.rain_dbz_proxy(qr, p, np.zeros_like(qr),
                                   np.full_like(qr, 0.01))
        self.assertTrue(np.isnan(result[0, 0, 0]))
        values = result[0, 1:, 0]
        self.assertTrue(np.all(np.diff(values) > 0))
        self.assertGreater(values[-1], 30.)

    def test_terrain_relative_height(self):
        ph = np.zeros((4, 2, 2))
        phb = np.broadcast_to(
            np.arange(4)[:, None, None] * 500 * 9.81, ph.shape
        )
        height = D.height_agl_mass(ph, phb)
        self.assertTrue(np.allclose(height[:, 0, 0], [250, 750, 1250]))
        field = np.broadcast_to(np.arange(3)[:, None, None], height.shape)
        self.assertTrue(np.all(D.near_height(field, height, 1000) == 1))


if __name__ == "__main__":
    unittest.main()
