"""Tests that validate configuration generation without installing/running WRF."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "make_namelists.py"


class GenerateNamelistsTest(unittest.TestCase):
    def generate(self, start="2026-10-13T12:00", hours=3):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        out = Path(temp.name) / "test-run"
        command = [
            sys.executable, str(SCRIPT),
            "--start", start, "--hours", str(hours),
            "--geog", "/path/to/WPS_GEOG", "--out", str(out),
        ]
        return subprocess.run(command, capture_output=True, text=True), out

    def test_smoke_profile(self):
        result, out = self.generate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("No atmospheric simulation was executed", result.stdout)
        wps = (out / "namelist.wps").read_text(encoding="utf-8")
        wrf = (out / "namelist.input").read_text(encoding="utf-8")
        self.assertIn("max_dom = 1", wps)
        self.assertIn("e_we = 81", wps)
        self.assertIn("dx = 9000", wps)
        self.assertIn("geog_data_res = 'lowres'", wps)
        self.assertIn("run_hours = 3", wrf)
        self.assertIn("num_metgrid_levels = 34", wrf)
        self.assertEqual(json.loads((out / "config.json").read_text())["hours"], 3)

    def test_crosses_midnight(self):
        result, out = self.generate("2026-12-31T18:00", 12)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("2027-01-01_06:00:00", (out / "namelist.wps").read_text())
        self.assertIn("end_year = 2027", (out / "namelist.input").read_text())

    def test_wps_real_met_em_soil_levels(self):
        """WPS met_em uses num_st_layers and num_sm_layers for GFS soils."""
        from unittest.mock import patch
        import importlib.util

        module_path = ROOT / "scripts" / "make_namelists.py"
        spec = importlib.util.spec_from_file_location("make_namelists", module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temp:
            met = Path(temp) / "met_em.d01.example.nc"
            met.touch()
            header = """netcdf met_em {
dimensions:
    num_metgrid_levels = 34 ;
    num_st_layers = 4 ;
    num_sm_layers = 4 ;
}
"""
            with patch.object(module.subprocess, "run") as run:
                run.return_value.stdout = header
                self.assertEqual(module.levels_from_met_em(met), (34, 4))
                run.return_value.stdout = header.replace(
                    "num_sm_layers = 4", "num_sm_layers = 2"
                )
                with self.assertRaisesRegex(ValueError, "inconsistent"):
                    module.levels_from_met_em(met)

    def test_invalid_cycle_fails(self):
        result, _ = self.generate("2026-10-13T13:00", 3)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("GFS cycle", result.stderr)


if __name__ == "__main__":
    unittest.main()
