"""Tests run without CUDA, Zig, WRF executables, Cartopy or original ARHT code."""
from __future__ import annotations

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import numpy as np

here = Path(__file__).resolve().parent
scripts_dir = here.parent / "scripts"
sys.path.insert(0, str(scripts_dir if (scripts_dir / "radar_lite.py").exists() else here))
import radar_lite as radar
import arht_lite_preflight as preflight


class TestRadarLite(unittest.TestCase):
    def test_aliasing(self):
        np.testing.assert_allclose(
            radar.fold_velocity(np.array([-33, -13, 0, 20, 31]), 25),
            [17, -13, 0, 20, -19])

    def test_demo_model_reads(self):
        from netCDF4 import Dataset
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "demo.nc"
            radar.make_demo(path, frames=3, grid=48)
            with Dataset(path) as ds:
                result = radar.sample_frame(ds, 1, range_km=85)
            self.assertEqual(result["dbz"].shape, (48, 48))
            self.assertTrue(result["has_velocity"])
            self.assertEqual(result["sampling_mode"], "model_height_sampled_ppi")
            self.assertGreater(result["max_dbz"], 35)
            self.assertLessEqual(float(np.nanmax(np.abs(result["velocity"]))), 27)

    def test_missing_refl_is_error(self):
        from netCDF4 import Dataset
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.nc"
            with Dataset(path, "w") as ds:
                ds.createDimension("Time", 1)
            with Dataset(path) as ds:
                with self.assertRaisesRegex(ValueError, "REFL_10CM"):
                    radar.sample_frame(ds, 0)

    def test_preflight_detects_missing_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ARHT.zip"
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("ARHT/arhtmodelviewer/cpu/kernels.py", "# test")
            report = preflight.inspect(path, ram_gb=8)
            self.assertEqual(report["status"], "BLOCKED_MISSING_RUNTIME")
            self.assertIn("arhtmodelviewer/cpu/runtime/cuda_cpu.h",
                          report["missing_critical_members"])
            self.assertFalse(report["executed_original_program"])


if __name__ == "__main__":
    unittest.main()
