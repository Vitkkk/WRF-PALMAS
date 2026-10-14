"""Unit tests for quick idealized cases, without compiling the Fortran model."""
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("prepare_ideal", ROOT / "scripts/prepare_ideal.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

STOCK = """ &time_control
 run_days = 0,
 run_hours = 0,
 run_minutes = 60,
 end_hour = 00, 00, 00,
 end_minute = 120, 120, 120,
 history_interval = 30, 10, 10,
 /
 &domains
 e_we = 42, 43, 43,
 e_sn = 42, 43, 43,
 e_vert = 41, 41, 41,
 ztop = 20000, 20000, 20000,
 /
"""


class PrepareIdealTest(unittest.TestCase):
    def test_one_hour(self):
        cfg = MODULE.make_namelist(STOCK, 60, 82, 10)
        self.assertIn("run_hours = 1,", cfg)
        self.assertIn("run_minutes = 0,", cfg)
        self.assertIn("end_hour = 1, 1, 1,", cfg)
        self.assertIn("end_minute = 0, 0, 0,", cfg)
        self.assertIn("e_we = 82, 82, 82,", cfg)
        self.assertIn("e_sn = 82, 82, 82,", cfg)
        self.assertIn("history_interval = 10, 10, 10,", cfg)
        self.assertIn("e_vert = 41, 41, 41,", cfg)

    def test_two_hours(self):
        cfg = MODULE.make_namelist(STOCK, 120, 42, 15)
        self.assertIn("run_hours = 2,", cfg)
        self.assertIn("end_hour = 2, 2, 2,", cfg)

    def test_reject_invalid(self):
        with self.assertRaises(ValueError):
            MODULE.make_namelist(STOCK, 90, 82, 10)
        with self.assertRaises(ValueError):
            MODULE.make_namelist(STOCK, 60, 82, 15 + 1)
        with self.assertRaises(ValueError):
            MODULE.make_namelist("nonsense", 60, 82, 10)


if __name__ == "__main__":
    unittest.main()
