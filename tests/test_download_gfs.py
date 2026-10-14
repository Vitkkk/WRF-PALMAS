"""Check that the GFS V0.5 request keeps all needed variable/level classes."""
import importlib.util
from pathlib import Path
import unittest
from urllib.parse import parse_qs, urlparse

PATH = Path(__file__).resolve().parents[1] / "scripts" / "download_gfs.py"
SPEC = importlib.util.spec_from_file_location("download_gfs", PATH)
D = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(D)


class GFSRequestTest(unittest.TestCase):
    def test_files_and_domain(self):
        for h in (0, 3):
            parsed = urlparse(D.build_url("20261013", "12", h))
            params = parse_qs(parsed.query, keep_blank_values=True)
            self.assertEqual(params["file"], [f"gfs.t12z.pgrb2.0p25.f{h:03d}"])
            self.assertEqual(params["dir"], ["/gfs.20261013/12/atmos"])
            self.assertEqual(params["all_lev"], ["on"])
            self.assertEqual(params["all_var"], ["on"])
            self.assertEqual(params["leftlon"], ["295"])
            self.assertEqual(params["rightlon"], ["320"])
            self.assertEqual(params["toplat"], ["-13"])
            self.assertEqual(params["bottomlat"], ["-43"])


if __name__ == "__main__":
    unittest.main()
