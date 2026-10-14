#!/usr/bin/env python3
"""Download two *real* GFS GRIB2 files from NOAA NOMADS for a WRF PALMAS pilot.

For a pilot, request a complete vertical-field inventory but only a South
American spatial subset. Run once, not in a retry storm against NOMADS.
"""
import argparse
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BASE = "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl"
BOX = {"leftlon": 295, "rightlon": 320, "toplat": -13,
       "bottomlat": -43}


def build_url(day: str, cycle: str, hour: int) -> str:
    file = f"gfs.t{cycle}z.pgrb2.0p25.f{hour:03d}"
    params = {
        "file": file, "all_var": "on", "all_lev": "on",
        "subregion": "", **BOX,
        "dir": f"/gfs.{day}/{cycle}/atmos",
    }
    return BASE + "?" + urllib.parse.urlencode(params)


def download(day: str, cycle: str, out: Path, hours=(0, 3)):
    chosen = datetime.strptime(day+cycle, "%Y%m%d%H").replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if chosen > now - timedelta(hours=4) or chosen < now-timedelta(days=9):
        raise ValueError("Choose an available GFS cycle 4 hours to 9 days old; no backfill here")
    out.mkdir(parents=True, exist_ok=True)
    for forecast in hours:
        url = build_url(day, cycle, forecast)
        target = out / f"gfs.t{cycle}z.pgrb2.0p25.f{forecast:03d}"
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers={
                    "User-Agent": "WRF-PALMAS-experimental/0.5 (+https://github.com/Vitkkk/WRF-PALMAS)"
                })
                with urllib.request.urlopen(req, timeout=150) as response:
                    with target.open("wb") as dest:
                        while chunk := response.read(1024 * 1024):
                            dest.write(chunk)
                if target.stat().st_size < 100000 or target.open("rb").read(4) != b"GRIB":
                    raise ValueError("GRIB2 response incomplete or unexpected")
                print(f"Downloaded {target.name}: {target.stat().st_size / 1e6:.1f} MB")
                break
            except Exception as err:
                target.unlink(missing_ok=True)
                if attempt == 2:
                    raise RuntimeError(f"NOMADS download failed for {target.name}: {err}") from err
                time.sleep(8 * (attempt + 1))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--day", required=True, help="YYYYMMDD UTC date")
    p.add_argument("--cycle", default="12", choices=("00", "06", "12", "18"))
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    download(a.day, a.cycle, a.out)
