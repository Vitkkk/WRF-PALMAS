#!/usr/bin/env python3
"""Generate a small, reproducible WRF/WPS experiment (does not run WRF)."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path


def parse_start(value: str) -> datetime:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M")
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use YYYY-MM-DDTHH:MM (UTC).") from exc
    if parsed.hour not in (0, 6, 12, 18) or parsed.minute:
        raise argparse.ArgumentTypeError("Use a 00, 06, 12 or 18 UTC GFS cycle.")
    return parsed.replace(tzinfo=timezone.utc)


def levels_from_met_em(path: Path) -> tuple[int, int]:
    """Use ncdump to read the actual metgrid dimensions, not guessed levels."""
    if not path.is_file():
        raise ValueError(f"met_em file does not exist: {path}")
    try:
        result = subprocess.run(
            ["ncdump", "-h", str(path)],
            capture_output=True, text=True, check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise ValueError("Install ncdump (netcdf-bin) and check the met_em file.") from exc
    levels = []
    for field in ("num_metgrid_levels", "num_metgrid_soil_levels"):
        match = re.search(rf"\b{field}\s*=\s*(\d+)\s*;", result.stdout)
        if not match:
            raise ValueError(f"Could not find {field} in {path}")
        levels.append(int(match.group(1)))
    return levels[0], levels[1]


def create_files(
    out: Path, start: datetime, hours: int, geog: str, grid: int,
    dx_km: int, lat: float, lon: float, cumulus: int,
    met_levels: int, soil_levels: int,
) -> None:
    end = start + timedelta(hours=hours)
    initial = start.strftime("%Y-%m-%d_%H:%M:%S")
    final = end.strftime("%Y-%m-%d_%H:%M:%S")
    dx = dx_km * 1000
    # Conservative starter value, not a universal CFL guarantee.
    time_step = dx_km * 4

    if "'" in geog:
        raise ValueError("Apostrophes in the geog path are not supported.")
    out.mkdir(parents=True, exist_ok=True)

    wps = f"""&share
 wrf_core = 'ARW',
 max_dom = 1,
 start_date = '{initial}',
 end_date = '{final}',
 interval_seconds = 10800,
 io_form_geogrid = 2,
/
&geogrid
 parent_id = 1,
 parent_grid_ratio = 1,
 i_parent_start = 1,
 j_parent_start = 1,
 e_we = {grid},
 e_sn = {grid},
 geog_data_res = 'lowres',
 dx = {dx},
 dy = {dx},
 map_proj = 'lambert',
 ref_lat = {lat},
 ref_lon = {lon},
 truelat1 = -30.0,
 truelat2 = -20.0,
 stand_lon = {lon},
 geog_data_path = '{geog}',
/
&ungrib
 out_format = 'WPS',
 prefix = 'FILE',
/
&metgrid
 fg_name = 'FILE',
 io_form_metgrid = 2,
/
"""

    # Fortran namelist values correspond to one, non-nested, real-data ARW domain.
    wrf = f"""&time_control
 run_days = 0,
 run_hours = {hours},
 run_minutes = 0,
 run_seconds = 0,
 start_year = {start.year},
 start_month = {start.month},
 start_day = {start.day},
 start_hour = {start.hour},
 end_year = {end.year},
 end_month = {end.month},
 end_day = {end.day},
 end_hour = {end.hour},
 interval_seconds = 10800,
 input_from_file = .true.,
 history_interval = 60,
 frames_per_outfile = 1,
 restart = .false.,
 io_form_history = 2,
 io_form_restart = 2,
 io_form_input = 2,
 io_form_boundary = 2,
/
&domains
 time_step = {time_step},
 max_dom = 1,
 e_we = {grid},
 e_sn = {grid},
 e_vert = 35,
 p_top_requested = 5000,
 num_metgrid_levels = {met_levels},
 num_metgrid_soil_levels = {soil_levels},
 dx = {dx},
 dy = {dx},
 grid_id = 1,
 parent_id = 1,
 i_parent_start = 1,
 j_parent_start = 1,
 parent_grid_ratio = 1,
 parent_time_step_ratio = 1,
 feedback = 1,
 smooth_option = 0,
/
&physics
 mp_physics = 8,
 ra_lw_physics = 4,
 ra_sw_physics = 4,
 radt = 15,
 sf_sfclay_physics = 1,
 sf_surface_physics = 2,
 bl_pbl_physics = 1,
 bldt = 0,
 cu_physics = {cumulus},
 cudt = 5,
 isfflx = 1,
 ifsnow = 1,
 icloud = 1,
 surface_input_source = 1,
 num_soil_layers = 4,
 sf_urban_physics = 0,
/
&dynamics
 w_damping = 0,
 diff_opt = 1,
 km_opt = 4,
 diff_6th_opt = 0,
 diff_6th_factor = 0.12,
 base_temp = 290.,
 damp_opt = 0,
 zdamp = 5000.,
 dampcoef = 0.2,
 khdif = 0,
 kvdif = 0,
 non_hydrostatic = .true.,
 moist_adv_opt = 1,
 scalar_adv_opt = 1,
/
&bdy_control
 spec_bdy_width = 5,
 specified = .true.,
 nested = .false.,
/
&namelist_quilt
 nio_tasks_per_group = 0,
 nio_groups = 1,
/
"""
    (out / "namelist.wps").write_text(wps, encoding="utf-8")
    (out / "namelist.input").write_text(wrf, encoding="utf-8")
    metadata = {
        "project": "WRF PALMAS", "profile": "smoke", "start_utc": start.isoformat(),
        "end_utc": end.isoformat(), "hours": hours,
        "grid_cells": [grid, grid], "spacing_km": dx_km,
        "domain_center": [lat, lon], "cumulus_scheme": cumulus,
        "metgrid_levels": met_levels, "soil_levels": soil_levels,
        "warning": "Only namelists generated. WRF/WPS and real weather data are required.",
    }
    (out / "config.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=parse_start, required=True,
                        help="GFS cycle UTC, YYYY-MM-DDTHH:MM, e.g. 2026-10-13T12:00")
    parser.add_argument("--hours", type=int, choices=(3, 6, 12), default=3)
    parser.add_argument("--geog", required=True, help="Existing WPS static geography directory")
    parser.add_argument("--out", type=Path, default=Path("runs/palmas-smoke"))
    parser.add_argument("--grid", type=int, default=81)
    parser.add_argument("--dx-km", type=int, default=9)
    parser.add_argument("--lat", type=float, default=-27.3)
    parser.add_argument("--lon", type=float, default=-52.3)
    parser.add_argument("--cumulus", type=int, choices=(0, 1), default=1)
    parser.add_argument("--met-em", type=Path,
                        help="Optional met_em NetCDF file: discover exact input/soil levels via ncdump")
    parser.add_argument("--met-levels", type=int, default=34,
                        help="Fallback only; MUST match the chosen GFS met_em file")
    parser.add_argument("--soil-levels", type=int, default=4,
                        help="Fallback only; MUST match the chosen GFS met_em file")
    args = parser.parse_args()

    if args.grid < 31 or args.grid > 301:
        parser.error("--grid must be between 31 and 301 for initial experiments")
    if args.dx_km < 3 or args.dx_km > 27:
        parser.error("--dx-km must be between 3 and 27")
    if not (-90 <= args.lat <= 90 and -180 <= args.lon <= 180):
        parser.error("Invalid latitude or longitude")
    if args.met_levels < 1 or args.soil_levels < 1:
        parser.error("Vertical level counts must be positive")
    try:
        levels = (levels_from_met_em(args.met_em) if args.met_em else
                  (args.met_levels, args.soil_levels))
        create_files(args.out, args.start, args.hours, args.geog, args.grid,
                     args.dx_km, args.lat, args.lon, args.cumulus, *levels)
    except ValueError as exc:
        parser.error(str(exc))
    print(f"Created namelist.wps, namelist.input and config.json in {args.out}")
    if not args.met_em:
        print("WARNING: Verify num_metgrid_levels and num_metgrid_soil_levels "
              "against met_em BEFORE running real.exe (or regenerate with --met-em).")
    print("No atmospheric simulation was executed.")


if __name__ == "__main__":
    main()
